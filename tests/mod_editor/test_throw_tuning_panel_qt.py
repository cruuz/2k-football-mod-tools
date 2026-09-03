"""The Throw Distance & Arc panel previews the game's own curve math and only
offers to write when the sliders differ from the source's current tables."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from mod_editor.gui.throw_tuning_panel_qt import ThrowTuningPanel  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402
from nfl2k5_edge_rename_test import build_edge_synthetic_xbe  # noqa: E402


class ThrowTuningPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.source = self.work / "default.xbe"
        self.source.write_bytes(_build_synthetic_xbe())
        self.panel = ThrowTuningPanel(None)
        self.addCleanup(self.panel.deleteLater)

    def test_starts_at_retail_with_a_live_preview(self) -> None:
        self.assertEqual(self.panel.settings(), tt.TuningSettings(55.0, 0.0))
        self.assertEqual(self.panel.preview_table.rowCount(), len(tt.PREVIEW_ARMS))
        top = self.panel.preview_table.item(len(tt.PREVIEW_ARMS) - 1, 2).text()
        self.assertEqual(top, "55 yd")
        self.assertFalse(self.panel.write_button.isEnabled())
        self.assertFalse(self.panel.target_button.isEnabled())

    def test_sliders_and_spins_stay_in_step_and_update_the_preview(self) -> None:
        self.panel.ceiling_slider.setValue(80)
        self.assertEqual(self.panel.ceiling_spin.value(), 80)
        self.panel.arc_spin.setValue(40)
        self.assertEqual(self.panel.arc_slider.value(), 40)
        self.assertEqual(self.panel.settings(), tt.TuningSettings(80.0, 0.4))
        rows = self.panel.preview_rows()
        self.assertEqual(rows[-1].deep_cap_yards, 80.0)
        self.assertAlmostEqual(rows[-1].hang_seconds, 5.0, places=2)
        last = len(tt.PREVIEW_ARMS) - 1
        self.assertEqual(self.panel.preview_table.item(last, 1).text(), "55 yd")
        self.assertEqual(self.panel.preview_table.item(last, 2).text(), "80 yd")
        self.assertEqual(self.panel.preview_table.item(last, 3).text(), "5.00 s")
        self.assertIn("lobspeed", self.panel.curves_label.text())

    def test_report_populates_fields_and_gates_the_write(self) -> None:
        self.panel.apply_report(tt.read_xbe(self.source))
        self.assertEqual(self.panel.source_field.text(), str(self.source.resolve()))
        self.assertIn("retail throw tables", self.panel.source_status.text())
        self.assertTrue(self.panel.target_button.isEnabled())
        self.assertFalse(self.panel.has_changes())
        self.assertFalse(self.panel.write_button.isEnabled())
        self.panel.target_field.setText(str(self.work / "out.xbe"))
        self.panel._refresh_controls()
        self.assertFalse(self.panel.write_button.isEnabled())
        self.panel.ceiling_spin.setValue(80)
        self.assertTrue(self.panel.has_changes())
        self.assertTrue(self.panel.write_button.isEnabled())
        self.panel.reset_to_retail()
        self.assertFalse(self.panel.has_changes())
        self.assertFalse(self.panel.write_button.isEnabled())

    def test_realistic_flight_and_catch_controls(self) -> None:
        self.panel.apply_report(tt.read_xbe(self.source))
        self.panel.target_field.setText(str(self.work / "out.xbe"))
        self.assertFalse(self.panel.has_changes())
        self.panel.realistic_check.setChecked(True)
        self.assertFalse(self.panel.arc_slider.isEnabled())
        self.assertTrue(self.panel.settings().realistic_flight)
        self.assertTrue(self.panel.has_changes())
        self.assertEqual(self.panel.preview_rows()[-1].hang_seconds, 2.81)  # 55 yd at 19.6 yd/s
        self.panel.realistic_check.setChecked(False)
        self.assertTrue(self.panel.arc_slider.isEnabled())
        self.assertFalse(self.panel.has_changes())
        self.assertTrue(self.panel.catch_check.isEnabled())
        self.panel.catch_check.setChecked(True)
        self.assertTrue(self.panel.catch_slider_requested())
        self.assertTrue(self.panel.has_changes())
        self.assertTrue(self.panel.write_button.isEnabled())
        self.panel.reset_to_retail()
        self.assertFalse(self.panel.catch_check.isChecked())
        self.assertFalse(self.panel.has_changes())

    def test_applied_catch_patch_is_shown_and_not_re_requested(self) -> None:
        patched = self.work / "patched.xbe"
        tt.write_xbe_copy(self.source, patched, catch_slider=True)
        self.panel.apply_report(tt.read_xbe(patched))
        self.assertTrue(self.panel.catch_check.isChecked())
        self.assertIn("catch patch applied", self.panel.source_status.text())
        self.assertFalse(self.panel.has_changes())

    def test_tuned_source_reports_its_sliders(self) -> None:
        tuned = self.work / "tuned.xbe"
        tt.write_xbe_copy(self.source, tuned, settings=tt.TuningSettings(72.0, 0.25))
        self.panel.apply_report(tt.read_xbe(tuned))
        self.assertEqual(self.panel.settings(), tt.TuningSettings(72.0, 0.25))
        self.assertIn("already tuned", self.panel.source_status.text())
        self.assertFalse(self.panel.has_changes())
        self.panel.arc_spin.setValue(0)
        self.assertTrue(self.panel.has_changes())

    def test_scorebug_checkbox_needs_a_retail_disc_image(self) -> None:
        # A bare default.xbe has no scorebug mesh: the control is off and disabled.
        self.panel.apply_report(tt.read_xbe(self.source))
        self.assertFalse(self.panel.scorebug_check.isEnabled())
        self.assertFalse(self.panel.scorebug_check.isChecked())
        self.assertIn("disc image", self.panel.scorebug_check.toolTip())
        # A disc image the layout tool cannot prove retail is refused (foreign), never guessed.
        report = dict(tt.read_xbe(self.source))
        report["container"] = "xiso"
        report["path"] = str(self.work / "missing.xiso.iso")
        self.panel.apply_report(report)
        self.assertEqual(self.panel._scorebug_state, "foreign")
        self.assertFalse(self.panel.scorebug_check.isEnabled())
        self.assertFalse(self.panel.has_changes())


if __name__ == "__main__":
    unittest.main()


class EdgeRenameCheckboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.work = Path(self._temporary.name)
        self.panel = ThrowTuningPanel(None)
        self.addCleanup(self.panel.deleteLater)

    def test_checkbox_is_disabled_when_the_sites_are_unrecognised(self) -> None:
        source = self.work / "default.xbe"
        source.write_bytes(_build_synthetic_xbe())   # no EDGE windows: foreign
        self.panel.apply_report(tt.read_xbe(source))
        self.assertFalse(self.panel.edge_check.isEnabled())
        self.assertFalse(self.panel.edge_check.isChecked())
        self.assertNotIn("EDGE rename", self.panel.source_status.text())

    def test_retail_sites_enable_the_checkbox_and_gate_the_write(self) -> None:
        source = self.work / "default.xbe"
        source.write_bytes(build_edge_synthetic_xbe())
        self.panel.apply_report(tt.read_xbe(source))
        self.assertTrue(self.panel.edge_check.isEnabled())
        self.assertIn("EDGE rename not applied", self.panel.source_status.text())
        self.panel.target_field.setText(str(self.work / "out.xbe"))
        self.panel._refresh_controls()
        self.assertFalse(self.panel.has_changes())
        self.panel.edge_check.setChecked(True)
        self.assertTrue(self.panel.has_changes())
        self.assertTrue(self.panel.write_button.isEnabled())
        self.panel.reset_to_retail()
        self.assertFalse(self.panel.edge_check.isChecked())
        self.assertFalse(self.panel.has_changes())

    def test_applied_source_shows_the_rename_and_locks_the_box(self) -> None:
        source = self.work / "default.xbe"
        target = self.work / "edge.xbe"
        source.write_bytes(build_edge_synthetic_xbe())
        tt.write_xbe_copy(source, target, edge_rename=True)
        self.panel.apply_report(tt.read_xbe(target))
        self.assertTrue(self.panel.edge_check.isChecked())
        self.assertFalse(self.panel.edge_check.isEnabled())
        self.assertIn("EDGE rename applied", self.panel.source_status.text())
        self.assertFalse(self.panel.has_changes())

