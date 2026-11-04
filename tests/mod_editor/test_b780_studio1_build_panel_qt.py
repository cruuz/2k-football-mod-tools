"""b780 studio1: Build tab bugs found by driving the real panel the way a player does (offscreen, no disc builds)."""

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

from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402


class _PanelCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "retail.xiso.iso"
        self.source.write_bytes(b"x" * 4096)

    def panel(self, **state_overrides) -> BuildPanel:
        panel = BuildPanel()
        self.addCleanup(self.app.processEvents)
        self.addCleanup(panel.deleteLater)
        state = {key: "retail" for key in panel._boxes()}
        state.update(path=str(self.source), container="xiso", throw=None, speed_threshold="retail")
        state.update(state_overrides)
        panel.apply_state(state)
        panel.target_field.setText(str(Path(self.tmp.name) / "out.xiso.iso"))
        self.app.processEvents()
        return panel


class SpeedSeparationIsCountedTests(_PanelCase):
    """Speed separation is a number row, not a check box, so the check-box walks (has_work, the change list) skipped it."""

    def test_the_strength_alone_is_work_and_is_named_in_every_summary(self) -> None:
        panel = self.panel()
        self.assertIn("Nothing is selected", panel.blocker())      # untouched: still a plain copy
        panel.speed_threshold_spin.setValue(40)
        self.app.processEvents()
        self.assertEqual(panel.plan().speed_threshold, 40)
        self.assertTrue(panel.has_work())
        self.assertNotIn("Nothing is selected", panel.blocker())
        self.assertIn("Speed separation (40)", panel.selected_labels())
        self.assertIn("Speed separation (40)", panel.summary_label.text())
        self.assertIn("Speed separation (40)", panel.confirmation_text(panel.plan()))
        self.assertTrue(panel.check_button.isEnabled())

    def test_the_strength_is_named_beside_other_changes(self) -> None:
        panel = self.panel()
        panel.cpu_clock2_check.setChecked(True)
        panel.speed_threshold_spin.setValue(70)
        self.app.processEvents()
        changes = [line for line in panel.confirmation_text(panel.plan()).splitlines() if line.startswith("Changes:")]
        self.assertEqual(len(changes), 1)
        self.assertIn("Speed separation (70)", changes[0])
        self.assertIn("Modern CPU clock management", changes[0])

    def test_zero_is_off_and_a_locked_row_is_not_a_change(self) -> None:
        panel = self.panel()
        self.assertEqual([label for label in panel.selected_labels() if "Speed separation" in label], [])
        # the disc already carries a strength: the row is locked at it and building on it changes nothing by itself
        locked = self.panel(speed_threshold="applied", speed_threshold_settings={"status": "applied", "value": 30})
        self.assertFalse(locked.speed_threshold_spin.isEnabled())
        self.assertEqual(locked.plan().speed_threshold, 30)
        self.assertFalse(locked.has_work())
        self.assertEqual([label for label in locked.selected_labels() if "Speed separation" in label], [])


class NeedsUpdateWordingTests(_PanelCase):
    """A beta-79 install that this build updates in place: the badge, the box and its tooltip must agree."""

    def test_boxes_that_stay_ticked_do_not_tell_the_player_to_select_them(self) -> None:
        panel = self.panel(honors_page="previous", k128_memory="previous", camera="previous")
        for key in ("honors_page", "k128_memory"):
            box = getattr(panel, key + "_check")
            self.assertTrue(box.isChecked() and not box.isEnabled(), key)           # locked on: the build updates it
            self.assertEqual(panel._badges[key].text(), "Needs update", key)
            self.assertNotIn("Select to update", box.toolTip(), key)
            self.assertIn("stays ticked", box.toolTip(), key)
            self.assertTrue(panel.plan().__dict__[key], key)
        camera = panel.camera_check                                                   # this one the player ticks
        self.assertTrue(camera.isEnabled() and not camera.isChecked())
        self.assertIn("Select to update", camera.toolTip())


class SpeedSeparationSurvivesAProjectSaveTests(_PanelCase):
    """The project is saved from the plan; a disabled row used to plan 0 even when no disc had been read yet."""

    def test_a_restored_strength_is_kept_by_a_save_made_before_the_disc_is_read(self) -> None:
        panel = BuildPanel()
        self.addCleanup(panel.deleteLater)
        panel.restore_project_build_settings({"speed_threshold": 60})
        self.assertFalse(panel.speed_threshold_spin.isEnabled())            # no disc read yet
        self.assertEqual(panel.project_build_settings()["speed_threshold"], 60)

    def test_it_is_still_zero_where_the_disc_cannot_take_it(self) -> None:
        for state in (dict(path="default.xbe", container="xbe", speed_threshold="retail"),
                      dict(path="d.iso", container="xiso", speed_threshold="foreign")):
            panel = self.panel()
            panel.speed_threshold_spin.setValue(60)
            panel.apply_state(state)
            panel.speed_threshold_spin.setValue(60)
            self.assertFalse(panel.speed_threshold_spin.isEnabled(), state)
            self.assertEqual(panel.plan().speed_threshold, 0, state)

    def test_a_read_disc_keeps_the_restored_strength(self) -> None:
        panel = self.panel()
        panel.restore_project_build_settings({"speed_threshold": 60})
        self.assertTrue(panel.speed_threshold_spin.isEnabled())
        self.assertEqual(panel.project_build_settings()["speed_threshold"], 60)


class StandaloneOptionsAreWorkTests(_PanelCase):
    """Options mod_build builds on their own were refused as "Nothing is selected" when they were the only tick."""

    def test_each_standalone_option_alone_is_a_change(self) -> None:
        for key in ("espn25_rosters", "honors_history", "trophy_room"):
            with self.subTest(option=key):
                panel = self.panel()
                box = panel._boxes()[key]
                self.assertTrue(box.isEnabled(), key)
                box.setChecked(True)
                self.app.processEvents()
                self.assertTrue(panel.has_work(), key)
                self.assertNotIn("Nothing is selected", panel.blocker(), key)
                self.assertTrue(panel.build_button.isEnabled(), panel.blocker())
                self.assertIn(box.text(), panel.selected_labels())

    def test_a_plain_copy_is_still_refused(self) -> None:
        panel = self.panel()
        self.assertFalse(panel.has_work())
        self.assertIn("Nothing is selected", panel.blocker())


class GameFixesFollowsBuildTests(unittest.TestCase):
    """Game Fixes and Build share one set of check boxes; the Build page owns the plan. A rule that fired on the other
    page while a copy was in flight used to be dropped, so Game Fixes showed unticked boxes the plan had ticked."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from mod_editor.gui.studio_qt import BrowseOnlyFacade, StudioMainWindow
        required = ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json"
        if not required.exists():
            raise unittest.SkipTest(f"Missing asset: {required}")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        source = Path(self.tmp.name) / "retail.xiso.iso"
        source.write_bytes(b"x" * 4096)
        self.window = StudioMainWindow(eager_pages=True, facade=BrowseOnlyFacade(), offer_recovery=False)
        self.addCleanup(self.app.processEvents)
        self.addCleanup(self.window.deleteLater)
        self.build, self.fixes = self.window._build_panel, self.window._gameplay_patches_panel
        state = {key: "retail" for key in self.build._boxes()}
        state.update(path=str(source), container="xiso", throw=None, speed_threshold="retail")
        for panel in (self.build, self.fixes):
            panel.apply_state(state)
        self.app.processEvents()

    def view(self, keys):
        return ([self.build._boxes()[key].isChecked() for key in keys], [self.fixes.checks[key].isChecked() for key in keys])

    def test_ticking_scorebug_effects_on_game_fixes_shows_what_the_plan_ticks(self) -> None:
        keys = ("scorebug_runtime", "scorebug", "xbe_space")
        self.fixes.checks["scorebug_runtime"].setChecked(True)
        self.app.processEvents()
        build_view, fixes_view = self.view(keys)
        self.assertEqual(build_view, [True, True, True])          # the rule on Build ticks the scorebug and the space
        self.assertEqual(fixes_view, build_view)
        self.assertTrue(self.build.plan().xbe_space)
        # and the other way: untick on Game Fixes; the parents stay on Build (they may serve other options) and both agree
        self.fixes.checks["scorebug_runtime"].setChecked(False)
        self.app.processEvents()
        build_view, fixes_view = self.view(keys)
        self.assertEqual(fixes_view, build_view)

    def test_random_ticks_on_either_page_never_leave_the_pages_apart(self) -> None:
        import random
        shared = sorted(set(self.build._boxes()) & set(self.fixes.checks))
        rng = random.Random(3)           # the seed that found it in five steps
        for step in range(150):
            if rng.random() < 0.06:
                self.build.apply_preset(rng.choice(("softdrink_basic", "softdrink_advanced", "softdrink_experimental")))
            else:
                key = rng.choice(shared)
                box = rng.choice((self.build._boxes()[key], self.fixes.checks[key]))
                if not box.isEnabled():
                    continue
                box.setChecked(not box.isChecked())
            self.app.processEvents()
            apart = [(key, self.build._boxes()[key].isChecked(), self.fixes.checks[key].isChecked()) for key in shared
                     if self.build._boxes()[key].isChecked() != self.fixes.checks[key].isChecked()]
            self.assertEqual(apart, [], f"step {step}")


if __name__ == "__main__":
    unittest.main()
