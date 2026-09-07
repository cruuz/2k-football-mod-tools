"""Standalone offscreen widget and worker wiring checks; no display or disc."""
import importlib.util
import os
from pathlib import Path
import sys
import time
import unittest
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HAVE_QT = importlib.util.find_spec("PyQt5") is not None


@unittest.skipUnless(HAVE_QT, "offscreen MyCareer page tests require PyQt5")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui import my_career_panel_qt as panel
        self.module = panel
        self.page = panel.MyCareerPanel()
        self.addCleanup(self.page.close)

    def finish(self):
        deadline = time.monotonic() + 5
        while self.page._task is not None and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertIsNone(self.page._task, "worker did not finish within 5 seconds")

    def test_no_implicit_write_and_missing_input_is_explained(self):
        with mock.patch.object(self.module.crib, "plan") as plan:
            self.page.set_source("source.iso")
            self.assertFalse(self.page.rebuild_button.isEnabled())
            self.assertIsNone(self.page._task)
            plan.assert_not_called()
        self.page._create()
        self.assertIn("first and last name", self.page.result.text())

    def test_setup_signal_and_worker_error_restore_controls(self):
        self.page.save.setText("source.zip")
        self.page.output.setText("new-folder")
        self.page.first.setText("My")
        self.page.last.setText("Player")
        delivered = []
        self.page.setup_ready.connect(delivered.append)
        with mock.patch.object(self.module.career, "prepare_save", return_value={"output": "new-folder", "myplayer": "My Player"}):
            self.page._create()
            self.finish()
        self.assertEqual(delivered, [str(Path("new-folder/MyCareer.json"))])
        self.assertIn("normal draft", self.page.result.text())
        with mock.patch.object(self.module.career, "prepare_save", side_effect=ValueError("draft stage required")):
            self.page._create()
            self.finish()
        self.assertEqual(self.page.result.text(), "draft stage required")
        self.assertTrue(self.page.create_button.isEnabled())

    def test_review_is_invalidated_when_image_changes(self):
        self.page.set_source("one.iso")
        with mock.patch.object(self.module.crib, "plan", return_value={"disc_bytes_reclaimed": 1024}):
            self.page._review()
            self.finish()
        self.assertTrue(self.page.rebuild_button.isEnabled())
        self.assertIn("Trophy Room", self.page.result.text())
        self.page.set_source("two.iso")
        self.assertIsNone(self.page._plan)
        self.assertFalse(self.page.rebuild_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
