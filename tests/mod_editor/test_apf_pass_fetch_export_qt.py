"""Offscreen pass-fetch input/worker/export regression tests."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication
from mod_editor.apf_studio import playbook_playcall_qt as ui
from mod_editor.core import apf2k8_playcall_patch as p
from mod_editor.core.errors import ValidationError
from test_apf_xex_image import synthetic_xex


class ExportPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        image = bytearray(p.IMAGE_SIZE)
        image[:2] = b"MZ"
        off = p.PROFILES[0].hook - p.IMAGE_BASE
        struct.pack_into(">I", image, off, 0x3D608506)
        cls.image = bytes(image)
        cls.profile = replace(p.PROFILES[0], sha256=hashlib.sha256(image).hexdigest(),
                              fetch_sha256=hashlib.sha256(image[off - 0x148:off + 0x30]).hexdigest())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = self.root / "game"; self.game.mkdir()
        self.source = self.game / "default.xex"; self.source.write_bytes(synthetic_xex(encrypted=True))
        self.settings = SimpleNamespace(title_update_path=None, xenia_path=None)
        self.facade = SimpleNamespace(source=SimpleNamespace(game_root=self.game, index_0a=self.game / "0A"),
                                      source_ready=False, last_build=SimpleNamespace(output_game=self.root / "build"),
                                      launcher=SimpleNamespace(settings=self.settings))
        self.tasks = []
        self.panel = ui.ApfPlaycallPanel(self.facade, lambda *args: self.tasks.append(args))

    def tearDown(self):
        self.panel.close(); self.panel.deleteLater()
        self.temp.cleanup()

    def complete_task(self):
        label, operation, done, blocking = self.tasks.pop(0)
        self.assertFalse(blocking)
        done(operation(lambda *args: None))
        return label

    def test_default_game_folder_and_expert_controls(self):
        self.assertEqual(self.panel.image_picker.currentText(), "Choose game folder")
        self.assertTrue(self.panel.update_button.isEnabled())
        self.panel.image_picker.setCurrentIndex(1)
        self.assertIn("Choose flat image", self.panel.image_picker.currentText())
        self.assertFalse(self.panel.update_button.isEnabled())
        self.assertIn("retail BASE or Title Update 1.1", self.panel.patch_note.text())
        self.assertIn("every down", self.panel.patch_note.text())
        self.assertIn("weighted picker", self.panel.patch_note.text())
        self.assertIn("next to your build", self.panel.patch_notice.text())

    def test_cancelled_folder_opens_no_worker_or_output_dialog(self):
        with patch.object(ui.QFileDialog, "getExistingDirectory", return_value="") as folder, \
                patch.object(ui.QFileDialog, "getSaveFileName") as save:
            self.panel.patch_button.click()
        self.assertEqual(folder.call_args.args[1], "Choose game folder")
        self.assertFalse(save.called)
        self.assertEqual(self.tasks, [])

    def test_both_routes_show_full_sha_refusal_without_output_dialog(self):
        flat = self.root / "image.pe"; flat.write_bytes(b"MZsynthetic-test")
        for mode in (0, 1):
            self.panel.image_picker.setCurrentIndex(mode)
            with patch.object(ui.QFileDialog, "getExistingDirectory", return_value=str(self.game)), \
                    patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(flat), "")), \
                    patch.object(ui.QFileDialog, "getSaveFileName") as save:
                self.panel.export_patch()
                self.assertFalse(self.panel.patch_button.isEnabled())
                self.complete_task()
                self.assertFalse(save.called)
            for digest in (hashlib.sha256(flat.read_bytes()).hexdigest(), *(r.sha256 for r in p.PROFILES)):
                self.assertIn(digest, self.panel.patch_notice.text())
            self.assertTrue(self.panel.patch_button.isEnabled())

    def test_success_suggests_build_neighbor_and_reparses_export(self):
        source_receipt = {"input_paths": [str(self.source)], "source_kind": "game_folder"}
        output = self.root / "chosen.patch.toml"
        with patch.object(ui.QFileDialog, "getExistingDirectory", return_value=str(self.game)), \
                patch.object(ui.QFileDialog, "getSaveFileName", return_value=(str(output), "")) as save, \
                patch.object(ui.game_image, "derive_image", return_value=(self.image, source_receipt)), \
                patch.object(p, "PROFILES", (self.profile,)):
            self.panel.export_patch()
            self.complete_task()
            self.assertEqual(Path(save.call_args.args[2]).parent, self.root)
            self.assertFalse(output.exists())  # publication has its own worker
            self.complete_task()
        self.assertIn("Read and checked retail BASE", self.panel.patch_notice.text())
        self.assertIn(str(output.resolve()), self.panel.patch_notice.text())
        self.assertIn("unwitnessed", self.panel.patch_notice.text())
        self.assertIn(self.profile.module_hash, output.read_text())
        self.assertTrue(self.panel.patch_button.isEnabled())

    def test_cancel_after_check_writes_nothing(self):
        with patch.object(ui.QFileDialog, "getExistingDirectory", return_value=str(self.game)), \
                patch.object(ui.QFileDialog, "getSaveFileName", return_value=("", "")), \
                patch.object(ui.game_image, "derive_image", return_value=(self.image, {"input_paths": [str(self.source)]})), \
                patch.object(p, "PROFILES", (self.profile,)):
            self.panel.export_patch(); self.complete_task()
        self.assertIn("export cancelled", self.panel.patch_notice.text())
        self.assertEqual(self.tasks, [])
        self.assertEqual(list(self.root.glob("*.toml")), [])

    def test_configured_and_explicit_updates_are_forwarded_only_for_game_mode(self):
        flat = self.root / "test.pe"; flat.write_bytes(self.image)
        configured, explicit = self.root / "TU_configured", self.root / "TU_explicit"
        self.settings.title_update_path = configured
        with patch.object(ui.QFileDialog, "getExistingDirectory", return_value=str(self.game)), \
                patch.object(ui.QFileDialog, "getOpenFileName", return_value=(str(flat), "")), \
                patch.object(ui.game_image, "derive_image", side_effect=ValidationError("test stop")) as derive:
            self.panel.export_patch(); self.complete_task()
            self.assertEqual(derive.call_args.kwargs["title_update"], configured)
            self.panel._title_update = explicit
            self.panel.export_patch(); self.complete_task()
            self.assertEqual(derive.call_args.kwargs["title_update"], explicit)
            self.panel.image_picker.setCurrentIndex(1)
            self.panel.export_patch(); self.complete_task()
            self.assertIsNone(derive.call_args.kwargs["title_update"])

    def test_busy_disables_all_export_choices(self):
        self.panel.set_busy(True)
        for widget in (self.panel.image_picker, self.panel.patch_button,
                       self.panel.update_button, self.panel.auto_update_button):
            self.assertFalse(widget.isEnabled())
        self.panel.set_busy(False)
        self.assertTrue(self.panel.patch_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
