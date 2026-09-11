"""Offscreen batch mapping dialog tests, standalone."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication, QDialogButtonBox
from mod_editor.apf_studio.ps3_texture_bundle import read_bundle
from mod_editor.apf_studio.ps3_texture_bundle_qt import Ps3BundleMappingDialog
from tests.mod_editor.test_apf_ps3_texture_bundle import bundle_files, slot, write_folder


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_hash_default_produces_two_distinct_layers(self):
        write_folder(self.root, bundle_files())
        dialog = Ps3BundleMappingDialog(read_bundle(self.root), [slot()])
        self.addCleanup(dialog.close)
        dialog.accept()
        self.assertEqual(len(dialog.plan.items), 2)
        self.assertEqual(dialog.plan.items[0].layer, "logo_l0")
        self.assertNotEqual(dialog.plan.items[0].image.tobytes(), dialog.plan.items[1].image.tobytes())

    def test_collision_requires_explicit_variant_selection(self):
        files = bundle_files()
        files.update({k.replace("/selected_", "/Alternative/selected_"): v for k, v in bundle_files().items()})
        write_folder(self.root, files)
        dialog = Ps3BundleMappingDialog(read_bundle(self.root), [slot()])
        self.addCleanup(dialog.close)
        button = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertFalse(button.isEnabled())
        dialog.rows[1][1].setChecked(False)
        self.assertTrue(button.isEnabled())
        dialog.accept()
        self.assertEqual(len(dialog.plan.assignments), 1)

    def test_missing_destination_does_not_accept(self):
        write_folder(self.root, bundle_files())
        dialog = Ps3BundleMappingDialog(read_bundle(self.root), [slot(hash_value=42)])
        self.addCleanup(dialog.close)
        dialog.rows[0][1].setChecked(True)
        dialog.accept()
        self.assertIsNone(dialog.plan)
        dialog.rows[0][2].setCurrentIndex(1)
        dialog.accept()
        self.assertIsNotNone(dialog.plan)

    def test_banner_bulk_selection_and_next_free_slot(self):
        files = bundle_files()
        files.update({k.replace("/selected_", "/Alternative/selected_"): v for k, v in bundle_files().items()})
        write_folder(self.root, files)
        dialog = Ps3BundleMappingDialog(read_bundle(self.root), [slot(), slot(hash_value=42, outer=1000)])
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        button = dialog.buttons.button(QDialogButtonBox.Ok)
        self.assertFalse(button.isEnabled())
        self.assertTrue(dialog.message.text())
        self.assertLess(dialog.message.geometry().bottom(), dialog.table.geometry().top())
        dialog.resolve_button.click()
        self.assertTrue(button.isEnabled())
        self.assertEqual(len({choices.currentData() for _, enabled, choices in dialog.rows if enabled.isChecked()}), 2)
        dialog.clear_button.click()
        self.assertTrue(all(not enabled.isChecked() for _, enabled, _ in dialog.rows))
        dialog.select_matched_button.click()
        self.assertTrue(all(enabled.isChecked() for _, enabled, _ in dialog.rows))


if __name__ == "__main__":
    unittest.main()
