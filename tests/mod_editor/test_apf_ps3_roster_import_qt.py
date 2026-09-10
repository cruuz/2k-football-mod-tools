"""Offscreen tests for the Import PS3 roster panel, standalone."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PyQt5.QtWidgets import QApplication, QMessageBox

from mod_editor.apf_studio import ps3_roster_convert as subject
from mod_editor.apf_studio.ps3_roster_import_qt import Ps3RosterImportPanel, XENIA_PLACEMENT
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture


def synchronous_run_task(title, operation, on_done, modal):
    result = operation(lambda message, done, total: None)
    if on_done is not None:
        on_done(result)
    return True


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        cls.fixture = Fixture()

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.panel = Ps3RosterImportPanel(synchronous_run_task)
        self.addCleanup(self.panel.close)

    def test_load_ps3_file_enables_import_and_converts_with_receipt(self) -> None:
        source = self.root / "USERDATA"
        source.write_bytes(self.fixture.ps3())
        self.assertFalse(self.panel.convert_button.isEnabled())
        self.panel.load_path(source)
        self.assertTrue(self.panel.convert_button.isEnabled())
        self.assertIn("PS3 layout detected", self.panel.summary_label.text())
        self.assertIn("2254 players", self.panel.summary_label.text())
        destination = self.root / "Roster.ROS"
        with mock.patch.object(QMessageBox, "information") as shown:
            self.panel.convert_to(destination)
        self.assertEqual(shown.call_count, 1)
        text = shown.call_args[0][2]
        self.assertIn("UNWITNESSED", text)
        self.assertIn(XENIA_PLACEMENT, text)
        self.assertIn("2254 players", text)
        receipt = self.panel.last_receipt
        self.assertIsNotNone(receipt)
        self.assertEqual(receipt.output, destination)
        self.assertEqual(destination.read_bytes(), self.fixture.expected())
        self.assertTrue(receipt.receipt_path.is_file())

    def test_xbox_layout_file_is_refused_without_writing(self) -> None:
        source = self.root / "Roster.ROS"
        source.write_bytes(self.fixture.expected())
        self.panel.load_path(source)
        self.assertFalse(self.panel.convert_button.isEnabled())
        self.assertIn("Already an Xbox 360 layout", self.panel.summary_label.text())
        self.assertEqual(self.panel.summary["platform"], subject.PLATFORM_XBOX360)


if __name__ == "__main__":
    unittest.main()
