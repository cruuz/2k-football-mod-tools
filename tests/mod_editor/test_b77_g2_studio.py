"""b77-g2 Studio settings: presets, plan fields and the Build page controls for the star gate."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build, modpack_sources  # noqa: E402
from mod_editor.core import nfl2k5_abilities_runtime as patch  # noqa: E402
from mod_editor.core import nfl2k5_build_settings as build_settings  # noqa: E402

try:
    from PyQt5.QtWidgets import QApplication
    from mod_editor.gui.build_panel_qt import BuildPanel
except ImportError:      # pragma: no cover
    BuildPanel = None

RULES = ("abilities_right_stick_stars_only", "abilities_charge_stars_only", "abilities_button_moves_stars_only")


class PlanTests(unittest.TestCase):
    def test_defaults_are_off_and_access_is_the_graded_table(self):
        plan = mod_build.BuildPlan(source=Path("a.xbe"), target=Path("b.xbe"))
        for key in RULES:
            self.assertIs(getattr(plan, key), False, key)
        self.assertEqual(tuple(plan.abilities_star_access), patch.DEFAULT_STAR_ACCESS)

    def test_presets_basic_off_modern_on_and_buttons_never(self):
        for preset, on in (("softdrink_basic", False), ("softdrink_advanced", True), ("softdrink_experimental", True)):
            plan = modpack_sources.build_plan(dict(preset=preset, overrides=dict(abilities=True)))
            self.assertIs(plan.abilities_right_stick_stars_only, on, preset)
            self.assertIs(plan.abilities_charge_stars_only, on, preset)
            self.assertFalse(plan.abilities_button_moves_stars_only, preset)
            self.assertEqual(tuple(plan.abilities_star_access), patch.DEFAULT_STAR_ACCESS, preset)
            self.assertFalse(plan.abilities_lock_right_stick or plan.abilities_lock_special_moves)

    def test_settings_are_saved_with_the_project(self):
        for key in (*RULES, "abilities_star_access"):
            self.assertIn(key, build_settings.FEATURE_KEYS)

    def test_charge_rule_refuses_the_legacy_move_locks_in_the_runtime(self):
        with self.assertRaises(ValueError):
            patch._stars(charge_stars_only="yes")
        with self.assertRaises(ValueError):
            patch.code_for(0x14DA000, charge_stars_only=True, lock_special_moves=True)


@unittest.skipIf(BuildPanel is None, "PyQt5 is required")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_controls_feed_the_plan_and_follow_the_abilities_option(self):
        panel = BuildPanel()
        try:
            self.assertEqual(set(panel.abilities_star_checks), set(RULES))
            self.assertEqual(len(panel.abilities_access_combos), 4)
            self.assertFalse(any(c.isEnabled() for c in panel.abilities_access_combos))
            panel.abilities_check.setEnabled(True)
            panel.abilities_check.setChecked(True)
            self.assertTrue(all(c.isEnabled() for c in panel.abilities_access_combos))
            panel.abilities_star_checks["abilities_charge_stars_only"].setChecked(True)
            panel.abilities_access_combos[0].setCurrentIndex(panel.abilities_access_combos[0].findData("charge"))
            plan = panel.plan()
            self.assertTrue(plan.abilities_charge_stars_only)
            self.assertEqual(tuple(plan.abilities_star_access), ("charge", "stick_charge", "full", "full"))
            self.assertEqual(panel.abilities_star_settings()["charge_stars_only"], True)
        finally:
            panel.deleteLater()
            self.app.processEvents()

    def test_installed_settings_set_the_controls(self):
        panel = BuildPanel()
        try:
            panel._apply_abilities_star_boxes({"right_stick_stars_only": True, "charge_stars_only": True})
            panel._apply_abilities_access(("none", "flicks", "stick_hurdle", "full"))
            self.assertEqual(panel.abilities_star_access(), ("none", "flicks", "stick_hurdle", "full"))
            self.assertTrue(panel.abilities_star_checks["abilities_right_stick_stars_only"].isChecked())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
