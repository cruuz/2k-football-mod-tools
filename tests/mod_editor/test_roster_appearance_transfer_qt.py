"""The roster panel's portable face export, load and disc-copy path."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests/mod_editor")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_roster_appearance_transfer as appearance
from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
from test_roster_appearance_transfer import fixture


class RosterAppearancePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_export_load_edit_and_write_copy_preserves_the_selected_face_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, catalog = fixture(root / "source", 0xA5)
            target, _ = fixture(root / "target", 0x3C)
            panel = RosterEditorPanel()
            try:
                with patch.object(appearance, "_catalog", return_value=catalog), \
                        patch.object(panel, "_reload_espn25"), patch.object(panel, "_load_templates"):
                    doc = rr.load_image(source.path)
                    doc.players[0].record.skin = 4
                    doc.players[0].record.set("face", 5)
                    panel.load_document(doc, source=source.path, kind="disc")
                    exported = panel.save_roster_with_faces_to(root / "faces.json")
                    self.assertEqual(len(exported["appearance_assets"]["resources"]), 6)
                    before = target.path.read_bytes()
                    panel.load_document(rr.load_image(target.path), source=target.path, kind="disc")
                    panel.load_roster_with_faces(root / "faces.json")
                    self.assertEqual(target.path.read_bytes(), before)
                    player = panel.document.players[0]
                    self.assertEqual((player.record.skin, player.record.get("face")), (4, 5))
                    player.record.set("speed", 95)
                    edited = panel.save_edits_to(root / "edited.json")
                    self.assertEqual(edited["appearance_assets"], exported["appearance_assets"])
                    output = root / "written.xiso.iso"
                    panel.write_copy_to(output)
                    self.assertEqual(rr.load_image(output).players[0].record.get("speed"), 95)
                    with rr._outer_image()(output) as archive:
                        self.assertEqual(appearance.prepare_writes(
                            archive, edited["appearance_assets"], rr.load_image(output).to_body()), [])
                    self.assertEqual(target.path.read_bytes(), before)
            finally:
                panel.deleteLater()
                self.application.processEvents()

    def test_save_without_disc_cannot_claim_it_contains_faces(self):
        panel = RosterEditorPanel()
        try:
            with self.assertRaisesRegex(rr.RosterRecordError, "source disc"):
                panel.save_roster_with_faces_to("unused.json")
            self.assertFalse(panel.export_roster_faces_action.isEnabled())
        finally:
            panel.deleteLater()
            self.application.processEvents()


if __name__ == "__main__":
    unittest.main()
