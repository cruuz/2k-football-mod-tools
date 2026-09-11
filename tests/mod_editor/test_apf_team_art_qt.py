"""Progressive thumbnails, source fences, filters and package inspector input."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PyQt5.QtCore import QCoreApplication, QEvent, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox
from mod_editor.apf_studio.apf_theme import install_theme
from mod_editor.apf_studio.models import Modification
from mod_editor.apf_studio.team_art_qt import TeamArtBrowser, TeamArtReplaceDialog
from tests.mod_editor.test_apf_team_art import package


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        install_theme(cls.app)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.png = Path(self.temp.name) / "thumb.png"
        Image.new("RGBA", (208, 128), "red").save(self.png)
        self.first = replace(package(), label="Americans", retail_teams=("Americans",))
        self.second = replace(package(), outer_index=990, catalog_index=99)
        self.packages = [self.first, self.second]
        self.facade = SimpleNamespace(source_ready=True, session=SimpleNamespace(modifications=(), asset_io=object()),
                                      team_art_packages=lambda _progress: tuple(self.packages))
        self.tasks = []
        self.browser = TeamArtBrowser(self.facade, lambda label, operation, done, blocking: self.tasks.append((label, operation, done)))
        self.browser.resize(1000, 570)
        self.browser.show()
        self.app.processEvents()
        self.addCleanup(self._destroy, self.browser)

    def _destroy(self, widget):
        # Delete Qt objects before interpreter exit; a widget outliving the QApplication segfaults at shutdown.
        widget.close()
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()

    def run_one(self):
        label, operation, done = self.tasks.pop(0)
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(operation, lambda *_args: None).result()
        done(result)
        self.app.processEvents()
        return label

    def test_grid_exists_before_worker_thumbnails_and_enter_opens_inspector(self):
        self.run_one()  # metadata
        self.assertEqual(self.browser.grid.count(), 2)
        self.assertTrue(self.tasks)
        gui_thread = threading.get_ident()
        def decode(*_args):
            self.assertNotEqual(threading.get_ident(), gui_thread)
            return self.png
        with patch("mod_editor.apf_studio.team_art_qt.thumbnail", side_effect=decode):
            self.run_one()
        self.assertEqual(len(self.browser._thumbs), 2)
        self.browser.grid.setCurrentRow(0)
        self.browser.grid.setFocus()
        QTest.keyClick(self.browser.grid, Qt.Key_Return)
        self.assertIs(self.app.focusWidget(), self.browser.layers)
        self.assertIn("logo_l0", self.browser.layers.toPlainText())
        self.assertIn("catalog 12", self.browser.layers.toPlainText())
        self.assertTrue(self.browser.replace_button.isEnabled())

    def test_filters_use_labels_retail_assignments_and_project_edits(self):
        self.run_one()
        self.browser.retail.setChecked(True)
        self.assertEqual(self.browser.grid.count(), 1)
        self.browser.retail.setChecked(False)
        self.browser.search.setText("990")
        self.assertEqual(self.browser.grid.count(), 1)
        self.browser.search.setFocus()
        QTest.keyClick(self.browser.search, Qt.Key_Escape)
        self.assertEqual(self.browser.grid.count(), 2)
        self.browser.staged.setChecked(True)
        self.assertEqual(self.browser.grid.count(), 0)
        self.facade.session.modifications = (Modification("crest", "helmet_crest_design", self.png, "a" * 64,
                                                          {"crest_outer_entry_index": 990}),)
        self.browser.refresh()
        self.assertEqual(self.browser.grid.count(), 1)
        self.assertIn("Staged", self.browser.grid.item(0).text())

    def test_late_thumbnail_cannot_repopulate_a_different_source(self):
        self.run_one()
        pending = self.tasks.pop()
        self.facade.source_ready = False
        self.facade.session = None
        self.browser.set_context()
        with patch("mod_editor.apf_studio.team_art_qt.thumbnail", return_value=self.png):
            pending[2](pending[1](lambda *_args: None))
        self.app.processEvents()
        self.assertEqual(self.browser.grid.count(), 0)
        self.assertEqual(self.browser._thumbs, {})

    def test_large_catalog_only_decodes_visible_rows_then_continues_on_scroll(self):
        self.packages.extend(replace(package(), outer_index=1000 + i, catalog_index=i) for i in range(60))
        self.run_one()
        self.assertEqual(self.browser.grid.count(), 62)
        with patch("mod_editor.apf_studio.team_art_qt.thumbnail", return_value=self.png):
            while self.tasks:
                self.run_one()
            decoded = len(self.browser._thumbs)
            self.assertGreater(decoded, 0)
            self.assertLess(decoded, 62)
            self.browser.grid.scrollToBottom()
            self.app.processEvents()
            self.assertTrue(self.tasks)
            while self.tasks:
                self.run_one()
        self.assertGreater(len(self.browser._thumbs), decoded)
        last = self.browser.grid.item(61).data(Qt.UserRole)
        self.assertTrue(any(key[0] == last.key for key in self.browser._thumbs))

    def test_pair_dialog_requires_each_png_and_digits_allow_subset(self):
        dialog = TeamArtReplaceDialog(self.first)
        self.addCleanup(self._destroy, dialog)
        stage = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertFalse(stage.isEnabled())
        dialog.inputs["logo_l0"].set_path(self.png)
        self.assertFalse(stage.isEnabled())
        dialog.inputs["logo_l1"].set_path(self.png)
        self.assertTrue(stage.isEnabled())
        digits = TeamArtReplaceDialog(package("number"))
        self.addCleanup(self._destroy, digits)
        digits.inputs["number_0_color"].set_path(self.png)
        self.assertTrue(digits.buttons.button(QDialogButtonBox.Ok).isEnabled())

    def test_short_inspector_preserves_preview_aspect_and_separates_layers(self):
        self.packages[0] = replace(self.first, label="Beasts, Cobras, Cougars, Gunslingers, Red Dogs")
        self.run_one()
        with patch("mod_editor.apf_studio.team_art_qt.thumbnail", return_value=self.png):
            self.run_one()
        self.browser.resize(1100, 420)
        self.browser.grid.setCurrentRow(0)
        self.app.processEvents()
        preview, layers = self.browser.preview, self.browser.layers
        self.assertEqual(preview.width(), 260)
        self.assertLess(preview.geometry().bottom(), layers.y())
        self.assertLess(layers.geometry().bottom(), self.browser.replace_button.y())
        rendered = preview.pixmap()
        self.assertLessEqual(rendered.height(), preview.contentsRect().height())
        self.assertAlmostEqual(rendered.width() / rendered.height(), 208 / 128, delta=.02)


if __name__ == "__main__":
    unittest.main()
