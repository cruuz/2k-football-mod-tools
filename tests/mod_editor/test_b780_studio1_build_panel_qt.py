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


if __name__ == "__main__":
    unittest.main()
