"""b780 studio1: Export roster edits answers in a dialog when it cannot export, instead of raising out of the click.

With a roster loaded together with its faces (Import roster with faces), staff changes cannot be exported yet, and
``edits_document`` says so with a RosterRecordError.  Every other button on the Rosters page turns such a refusal into a
dialog; this one let it out of the slot, so the player saw the Studio's crash report instead of "Put every coach back...".
Synthetic three club roster, no disc.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication, QFileDialog  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui import roster_editor_panel_qt as page_module  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel  # noqa: E402
from b780_staff_fixture import synthetic_staff_body  # noqa: E402


class ExportRosterEditsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.panel = RosterEditorPanel()
        self.addCleanup(self.panel.deleteLater)
        self.panel.load_document(rr.load_body(synthetic_staff_body()), label="synthetic disc")
        self.app.processEvents()
        self.assertTrue(self.panel.coaches_panel.swap_clubs("SF", "CHI"))

    def click_export(self, target: Path):
        with mock.patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
                mock.patch.object(page_module, "show_operation_error") as shown:
            self.panel._save_edits()
        return shown

    def test_staff_changes_on_a_roster_with_faces_are_a_dialog_not_an_exception(self) -> None:
        self.panel._appearance_bundle = {"schema": "faces"}
        target = Path(self.temp.name) / "edits.json"
        shown = self.click_export(target)
        shown.assert_called_once()
        operation, message = shown.call_args.args[1], shown.call_args.args[2]
        self.assertEqual(operation, "export the roster edits")
        self.assertIn("Put every coach back on the Coaches tab", message)
        self.assertFalse(target.exists())

    def test_a_path_that_cannot_be_written_is_a_dialog_too(self) -> None:
        shown = self.click_export(Path(self.temp.name) / "no such folder" / "edits.json")
        shown.assert_called_once()

    def test_a_good_export_writes_the_staff_and_shows_nothing(self) -> None:
        target = Path(self.temp.name) / "edits ü.json"
        shown = self.click_export(target)
        shown.assert_not_called()
        document = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(len(document["staff"]["head_coaches"]), 2)


if __name__ == "__main__":
    unittest.main()
