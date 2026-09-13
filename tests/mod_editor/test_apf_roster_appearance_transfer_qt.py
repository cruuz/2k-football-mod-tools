"""Offscreen, synthetic end-to-end Custom Team Appearance transfer action."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication, QFileDialog
from mod_editor.apf_studio.custom_team_appearance_qt import CustomTeamAppearancePanel
from mod_editor.apf_studio.roster_appearance_transfer_qt import RosterAppearanceTransferDialog
from tests.mod_editor.test_apf_custom_team_appearance_gui import _Facade, _run_task
from tests.test_apf_save_custom_team_appearance import synthetic_save, synthetic_stfs, writer
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture


class TransferGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.facade = _Facade()
        self.panel = CustomTeamAppearancePanel(self.facade, _run_task)
        self.addCleanup(self.panel.close)

    def test_page_button_transfers_controls_and_other_staged_slots(self):
        self.facade.replace_custom_team_appearance(self.facade.values[33], lambda *_: None)
        self.panel.home.palette[0].setText("FF123456")
        source = self.root / "Roster.ROS"
        raw = synthetic_save()
        source.write_bytes(raw)
        destination = self.root / "new.ROS"

        def drive(dialog):
            self.assertFalse(dialog.include_staged.isChecked())
            self.assertFalse(dialog.write_button.isEnabled())
            with mock.patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")):
                dialog.choose_button.click()
            self.assertIn("Slot 32", dialog.targets.text())
            dialog.include_staged.setChecked(True)
            self.assertIn("Slot 33", dialog.targets.text())
            with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(destination), "")):
                dialog.write_button.click()
            self.assertEqual(dialog.last_receipt.changed_slots, (32, 33))
            self.assertIn("UNWITNESSED", dialog.status.text())
            return 0

        with mock.patch.object(RosterAppearanceTransferDialog, "exec_", drive):
            self.panel.apply_roster_button.click()
        self.assertEqual(source.read_bytes(), raw)
        self.assertEqual(writer.parse_save(destination.read_bytes()).slots[0].appearance.home.palette[0], 0xFF123456)
        self.assertEqual(self.panel.home.palette[0].text(), "FF123456")
        self.assertEqual(self.facade.modified_asset_ids, frozenset({"apf:custom-team-appearance:33"}))

    def test_xenia_output_is_explicit_off_by_default_and_reparsed(self):
        source = self.root / "source.stfs"
        source.write_bytes(synthetic_stfs(synthetic_save(), copies=2, active=1))
        dialog = RosterAppearanceTransferDialog(self.facade.values[32], (), _run_task)
        self.addCleanup(dialog.close)
        dialog.load_path(source)
        self.assertFalse(dialog.output_kind.currentData())
        self.assertEqual(dialog.output_kind.count(), 2)
        dialog.output_kind.setCurrentIndex(1)
        self.assertIn("Xenia only; a real console will reject this package", dialog.boundary.text())
        self.assertIn("HYPOTHESIS", dialog.boundary.text())
        output = self.root / "new.stfs"
        dialog.write_to(output)
        receipt = json.loads(dialog.last_receipt.manifest.read_text())
        self.assertTrue(receipt["verification"]["stfs_rehash_reverified"])
        self.assertFalse(receipt["stfs_rehash"]["console_resigned"])

    def test_ps3_conversion_then_editor_appearance(self):
        source = self.root / "USERDATA"
        source.write_bytes(Fixture().ps3())
        dialog = RosterAppearanceTransferDialog(self.facade.values[32], (), _run_task)
        self.addCleanup(dialog.close)
        dialog.load_path(source)
        self.assertEqual(dialog.output_kind.count(), 1)
        self.assertIn("Converts PS3 first", dialog.boundary.text())
        output = self.root / "new.ROS"
        dialog.write_to(output)
        self.assertTrue(dialog.last_receipt.converted_ps3)
        self.assertEqual(writer.parse_save(output.read_bytes()).slots[0].appearance, self.facade.values[32])


if __name__ == "__main__":
    unittest.main()
