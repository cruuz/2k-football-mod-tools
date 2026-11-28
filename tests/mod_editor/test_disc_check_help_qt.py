"""Exercise the real menu, dialog, worker and support clipboard."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from PyQt5.QtCore import QTimer
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QFileDialog

from mod_editor.core import nfl2k5_disc_check as checker
from mod_editor.gui.studio_qt import StudioMainWindow
from tests.mod_editor.test_xiso_layout_tolerance import build_xdvdfs


class DiscCheckHelpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.window = StudioMainWindow(offer_recovery=False)
        self.window.show()
        self.addCleanup(self.window.deleteLater)
        menu = next(action.menu() for action in self.window.menuBar().actions() if action.text() == "&Help")
        self.action = next(action for action in menu.actions() if action.text() == "Check my SOFTDRINK disc…")
        self.image = Path(self.temp.name) / "München Save Disc.xiso.iso"

    def wait(self, condition):
        deadline = time.monotonic() + 8
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition())

    def test_real_menu_comparison_is_responsive_and_copies_release_and_details(self):
        self.image.write_bytes(build_xdvdfs({"default.xbe": b"XBEH" + bytes(4096), "assets.bin": b"art"}))
        entry = checker.make_entry("SOFTDRINK test (64 MB)", self.image)
        release = threading.Event()
        entered = threading.Event()
        threads = []
        def load_releases():
            threads.append(threading.get_ident())
            entered.set()
            self.assertTrue(release.wait(5))
            return [entry]
        with patch.object(checker, "load_releases", side_effect=load_releases), \
                patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.image), "")) as choose:
            self.action.trigger()
            self.wait(entered.is_set)
            dialog = self.window._disc_check_dialog
            try:
                self.assertTrue(self.window._blocking)
                self.assertFalse(self.action.isEnabled())
                self.window._choose_disc_check()
                choose.assert_called_once()
                self.assertNotEqual(threads[0], threading.get_ident())
                tick = []
                QTimer.singleShot(0, lambda: tick.append(True))
                self.wait(lambda: bool(tick))
            finally:
                release.set()
            self.wait(lambda: not self.window._blocking)
        self.assertTrue(self.action.isEnabled())
        self.assertTrue(dialog.report.isReadOnly())
        self.assertIn("matches SOFTDRINK test (64 MB) file for file", dialog.report.toPlainText())
        self.assertIn(self.image.name, dialog.report.toPlainText())
        self.assertNotIn(str(self.image.parent), dialog.report.toPlainText())
        dialog.copy_button.click()
        self.assertEqual(self.app.clipboard().text(), dialog.report.toPlainText())
        dialog.close_button.click()
        self.assertIsNone(self.window._disc_check_dialog)

    def test_cancelled_picker_and_unreadable_image(self):
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
            self.action.trigger()
        self.assertFalse(self.window._blocking)
        self.assertIsNone(getattr(self.window, "_disc_check_dialog", None))
        self.image.write_bytes(b"not an Xbox image")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.image), "")):
            self.action.trigger()
            self.wait(lambda: not self.window._blocking)
        dialog = self.window._disc_check_dialog
        self.assertIn("readable Xbox disc image", dialog.report.toPlainText())
        self.assertTrue(dialog.copy_button.isVisible())
        dialog.close_button.click()

    def test_changed_file_is_named_in_the_support_report(self):
        files = {"default.xbe": b"XBEH" + bytes(8192), "faces.bin": b"good"}
        self.image.write_bytes(build_xdvdfs(files))
        release = checker.make_entry("SOFTDRINK test (128 MB)", self.image)
        self.image.write_bytes(build_xdvdfs({**files, "faces.bin": b"oops"}))
        with patch.object(checker, "load_releases", return_value=[release]), \
                patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.image), "")):
            self.action.trigger()
            self.wait(lambda: not self.window._blocking)
        dialog = self.window._disc_check_dialog
        dialog.copy_button.click()
        self.assertIn("damaged or incomplete", self.app.clipboard().text())
        self.assertIn("faces.bin differs", self.app.clipboard().text())
        dialog.close_button.click()

    def _stop_check(self, close_studio):
        started = threading.Event()
        proceed = threading.Event()
        def hashing(_image, *, progress):
            started.set()
            self.assertTrue(proceed.wait(5))
            progress("Hashing game files", 1, 2)
            self.fail("The verifier should stop at its next progress callback.")
        with patch.object(checker, "check", side_effect=hashing), \
                patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.image), "")):
            self.action.trigger()
            self.wait(started.is_set)
            dialog = self.window._disc_check_dialog
            try:
                if close_studio:
                    self.window.close()
                else:
                    dialog.close_button.click()
                self.assertTrue(dialog.cancellation.is_set())
                self.assertTrue(self.window._blocking)
            finally:
                proceed.set()
            self.wait(lambda: not self.window._blocking)
            self.assertIsNone(self.window._disc_check_dialog)
        self.assertEqual(self.window.isVisible(), not close_studio)

    def test_cancel_releases_the_slot_for_a_second_check(self):
        self._stop_check(False)
        self.assertTrue(self.action.isEnabled())

    def test_closing_studio_stops_a_check_before_closing_the_window(self):
        self._stop_check(True)


if __name__ == "__main__":
    unittest.main()
