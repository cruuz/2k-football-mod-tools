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

class IntegrationBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def panel(self):
        panel = BuildPanel()
        self.addCleanup(panel.deleteLater)
        state = {key: "retail" for key in panel._boxes()}
        state.update(path="retail.iso", container="xiso", throw=None)
        panel.apply_state(state)
        return panel

    def test_experimental_flags_roundtrip_and_clear_on_preset_switch(self):
        plan = mod_build.BuildPlan("source.iso", "copy.iso", xbe_space=True, kickoff_relocated=True)
        for name, season, cap, screen in (("softdrink_experimental", True, True, "D"),
                                         ("softdrink_advanced", False, False, None),
                                         ("softdrink_basic", False, False, None)):
            plan = mod_build.apply_preset(plan, name)
            restored = mod_build.BuildPlan("source.iso", "copy.iso", **plan.to_recipe())
            self.assertEqual((restored.season_cap, restored.guardian_cap, restored.screen_timing),
                             (season, cap, screen))
            self.assertFalse(restored.xbe_space or restored.kickoff_relocated)
        for key, value in (("guardian_cap", True), ("screen_timing", "A")):
            self.assertFalse(mod_build.BuildPlan("s", "t", **{key: value}).wants_xbe_patch())

    def test_each_checkbox_reaches_plan_and_work_predicate(self):
        panel = self.panel()
        for key in ("season_cap", "guardian_cap", "screen_timing", "xbe_space", "kickoff_relocated", "depth_locks"):
            box = panel._boxes()[key]
            self.assertTrue(box.isEnabled(), key)
            box.setChecked(True)
            self.assertEqual(getattr(panel.plan(), key), "D" if key == "screen_timing" else True)
            self.assertTrue(panel.has_work(), key)
            box.setChecked(False)
        self.assertFalse(panel.has_work())

    def test_screen_level_change_preserves_other_choices_and_detects_foreign_level(self):
        from unittest.mock import patch
        from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel
        for panel in (self.panel(), GameplayPatchesPanel()):
            self.addCleanup(panel.deleteLater)
            boxes = panel._boxes() if isinstance(panel, BuildPanel) else panel.checks
            state = {key: "retail" for key in boxes}
            state.update(path="retail.iso", container="xiso", throw=None)
            panel.apply_state(state)
            boxes["season_cap"].setChecked(True)
            boxes["screen_timing"].setChecked(True)
            with patch.object(mod_build, "inspect_screen_timing", return_value={"status":"retail", "level":"A", "books":[]}) as inspect:
                panel.screen_timing_combo.setCurrentText("A")
                inspect.assert_called_once_with("retail.iso", "A")
            self.assertTrue(panel.plan().season_cap)
            self.assertEqual(panel.plan().screen_timing, "A")
            with patch.object(mod_build, "inspect_screen_timing", return_value={"status":"foreign", "level":"B", "books":[]}):
                panel.screen_timing_combo.setCurrentText("B")
            self.assertFalse(boxes["screen_timing"].isEnabled())
            self.assertIsNone(panel.plan().screen_timing)
            self.assertTrue(panel.plan().season_cap)

    def test_screen_invalid_levels_refuse_before_copy(self):
        from unittest.mock import patch
        for level in (True, False, "", "E", 1):
            with patch.object(mod_build.shutil, "copyfile") as copy:
                with self.assertRaisesRegex(ValueError, "screen_timing"):
                    mod_build._build(mod_build.BuildPlan("s", "t", screen_timing=level))
                copy.assert_not_called()

    def test_image_only_features_are_gated_but_season_cap_accepts_xbe(self):
        panel = self.panel()
        state = {key: "retail" for key in panel._boxes()}
        state.update(path="default.xbe", container="xbe", throw=None)
        panel.apply_state(state)
        self.assertTrue(panel.season_cap_check.isEnabled())
        for key in ("guardian_cap", "screen_timing", "xbe_space", "kickoff_relocated"):
            self.assertFalse(panel._boxes()[key].isEnabled(), key)

    def test_modern_defense_shortcut_deduplicates_explicit_choice(self):
        panel = self.panel()
        self.assertEqual(panel.plan().playbook_packs, ())
        panel._add_modern_defense_pack()
        panel._add_modern_defense_pack()
        self.assertEqual(len(panel.plan().playbook_packs), 1)
        self.assertTrue(panel.plan().playbook_packs[0].endswith("softdrink_modern_defense.2k5book"))


if __name__ == "__main__":
    unittest.main()
