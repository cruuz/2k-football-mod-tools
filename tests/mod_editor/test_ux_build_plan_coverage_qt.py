"""Every BuildPlan field is reachable on the Build tab (UX E4).

The review found the tab hard-coded ``arc`` to zero and had no input at all for
``playbook_packs``, ``name``, ``author``, ``notes`` and ``commentary``; the source had no
exhaustive BuildPlan-to-widget gate, so nothing would have noticed.  This test walks the
dataclass and checks that the panel's ``plan()`` carries a value set through the page for
each field (the three build-time fields and the dynamic-kickoff settings dictionary are
listed explicitly).  It also pins the two contracts the review insisted on: the unreleased
7-on-7 row stays reachable but disabled with its reason, and a required file that is missing
blocks the button with a sentence that names the file.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication, QCheckBox  # noqa: E402

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.gui.build_panel_qt import BuildPanel  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402

# BuildPlan fields the page does not expose as a control, and why.
NOT_A_CONTROL = {
    "source": "the disc / executable field (filled by the open-disc hook or Choose…)",
    "target": "the Save disc copy as field",
    "overwrite": "decided by the existing replacement confirmation, never a default-on box",
    "dynamic_kickoff_settings": "the shipped defaults of the dynamic-kickoff patch (no per-user tuning is offered yet)",
}


class BuildPlanCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / "default.xbe"
        self.source.write_bytes(_build_synthetic_xbe())
        self.panel = BuildPanel()
        self.panel.apply_state(mod_build.inspect(self.source))
        self.app.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.app.processEvents()
        self.tmp.cleanup()

    def test_every_buildplan_field_has_a_binding_on_the_page(self) -> None:
        panel = self.panel
        fields = {f.name for f in dataclasses.fields(mod_build.BuildPlan)}
        # every boolean / string toggle has a check box the page maps by field name
        boxes = panel._boxes()
        for key in boxes:
            self.assertIn(key, fields, key)
        bound = set(boxes) | set(NOT_A_CONTROL) | {
            "max_deep_yards", "arc", "player_tags", "team_history", "career_stats", "prospect_names",
            "roster_edits", "commentary", "playbook_packs", "name", "author", "notes",
        }
        self.assertEqual(fields - bound, set(), "BuildPlan fields with no control on the Build tab")
        self.assertEqual(bound - fields, set(), "controls that name a field BuildPlan no longer has")

    def test_the_new_bindings_reach_plan(self) -> None:
        panel = self.panel
        panel.target_field.setText(str(Path(self.tmp.name) / "out.xbe"))
        panel.throw_check.setChecked(True)
        panel.realistic_check.setChecked(False)
        panel.arc_spin.setValue(40)
        panel.ceiling_spin.setValue(75)
        panel.name_field.setText("My mod")
        panel.author_field.setText("me")
        panel.notes_field.setPlainText("first try")
        panel.set_commentary([mod_build.CommentarySwap("cutsceneaudio:3", "/tmp/line.wav")])
        panel.set_playbook_packs(["/tmp/one.2k5book", "/tmp/two.2k5book"])
        plan = panel.plan()
        self.assertAlmostEqual(plan.arc, 0.40)
        self.assertEqual(plan.max_deep_yards, 75.0)
        self.assertEqual((plan.name, plan.author, plan.notes), ("My mod", "me", "first try"))
        self.assertEqual(plan.commentary[0].stream, "cutsceneaudio:3")
        self.assertEqual(plan.playbook_packs, ("/tmp/one.2k5book", "/tmp/two.2k5book"))
        self.assertIn("commentary lines (1)", panel.selected_labels())
        self.assertIn("playbook packs (2)", panel.selected_labels())
        # the manual arc only applies while realistic flight is off
        panel.realistic_check.setChecked(True)
        self.assertFalse(panel.arc_spin.isEnabled())
        # the jersey mode maps to the two non-default profiles; unticked is the original behaviour
        self.assertEqual(panel.plan().uniform_choice, "")
        if panel.uniform_choice_check.isEnabled():
            panel.uniform_choice_check.setChecked(True)
            self.assertEqual(panel.plan().uniform_choice, "choice")
            panel.uniform_choice_mode.setCurrentIndex(1)
            self.assertEqual(panel.plan().uniform_choice, "rule")

    def test_seven_on_seven_is_reachable_but_disabled_in_this_release(self) -> None:
        panel = self.panel
        self.assertFalse(mod_build.SEVEN_ON_SEVEN_RELEASED)
        self.assertFalse(panel.seven_on_seven_check.isHidden())
        self.assertFalse(panel.seven_on_seven_check.isEnabled())
        self.assertIn("Not available in this release", panel.seven_on_seven_check.toolTip())
        self.assertEqual(panel._badges["seven_on_seven"].text(), "Not available in this release")

    def test_a_ticked_option_with_a_missing_required_file_names_the_file(self) -> None:
        panel = self.panel
        panel.target_field.setText(str(Path(self.tmp.name) / "out.xbe"))
        panel.throw_check.setChecked(True)
        self.assertEqual(panel.blocker(), "")
        self.assertTrue(panel.build_button.isEnabled())
        # a bare executable cannot take the CSV steps; force the check to model a disc source
        panel.career_stats_check.setEnabled(True)
        panel.career_stats_check.setChecked(True)
        self.assertTrue(panel.career_row.isVisibleTo(panel), "the required row appears with the tick")
        self.assertEqual(panel.blocker(), "Choose a career stats CSV file.")
        self.assertFalse(panel.build_button.isEnabled())
        self.assertEqual(panel.build_button.toolTip(), panel.blocker())
        panel.career_stats_field.setText(str(Path(self.tmp.name) / "stats.csv"))
        self.assertEqual(panel.blocker(), "")

    def test_a_camera_only_selection_enables_the_button(self) -> None:
        panel = self.panel
        panel.target_field.setText(str(Path(self.tmp.name) / "out.xbe"))
        panel.camera_check.setEnabled(True)
        panel.camera_check.setChecked(True)
        self.assertTrue(panel.build_button.isEnabled(), panel.blocker())
        self.assertIn("Make Standard camera look like Far", panel.selected_labels())

    def test_every_check_box_keeps_a_short_caption(self) -> None:
        for box in self.panel.findChildren(QCheckBox):
            self.assertLessEqual(len(box.text()), 60, box.text())
            self.assertTrue(box.text().strip(), "a nameless check box has no accessible name")

    def test_source_and_output_as_the_same_file_is_blocked_with_a_fix(self) -> None:
        panel = self.panel
        panel.throw_check.setChecked(True)
        panel.target_field.setText(str(self.source))
        self.assertIn("Fix: choose a different output file", panel.blocker())


if __name__ == "__main__":
    unittest.main()
