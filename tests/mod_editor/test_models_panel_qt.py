"""The ★ Models page: gating, text helpers, and its place in the studio shell."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_models as M  # noqa: E402
from mod_editor.gui.models_panel_qt import (  # noqa: E402
    FEASIBILITY, ModelsPanel, import_report_text, set_report_text,
)

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
PACK0 = EXTRACTION / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"
INVENTORY = REPO / "reports" / "assets" / "nfl2k5_resource_chunks_v2.json"
HAVE_DISC = PACK0.is_file() and INVENTORY.is_file()


class ModelsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = ModelsPanel()

    def tearDown(self) -> None:
        self.panel.wait_idle(20_000)
        self.app.processEvents()
        self.panel.deleteLater()
        self.app.processEvents()

    def test_nothing_is_enabled_before_a_disc(self) -> None:
        panel = self.panel
        self.assertFalse(panel.export_button.isEnabled())
        self.assertFalse(panel.check_button.isEnabled())
        self.assertFalse(panel.write_button.isEnabled())
        self.assertFalse(panel.reload_button.isEnabled())
        panel.reload()
        self.assertIn("Load your NFL 2K5 XISO", panel.status_label.text())

    def test_feasibility_text_names_the_boundaries(self) -> None:
        for phrase in ("EXPORT", "IMPORT", "NOT YET", "vertex count", "Attributes", "hi_body",
                       "PLAYER BODY SET", "lo_body", "ONE copy"):
            self.assertIn(phrase, FEASIBILITY)

    def test_the_body_set_box_is_off_until_a_member_is_selected(self) -> None:
        panel = self.panel
        self.assertFalse(panel.export_set_button.isEnabled())
        self.assertFalse(panel.check_set_button.isEnabled())
        self.assertIsNone(panel.current_body_set())
        self.assertIn("three models", panel.set_label.text())

    def test_selecting_a_member_arms_the_body_set_box(self) -> None:
        panel = self.panel
        entries = [M.ModelEntry(M.model_key(3, c), 3, c, name, "players", 10, 20)
                   for c, name in ((113, "lo_body"), (114, "hi_body"), (115, "hi_head"), (88, "ball"))]
        panel.apply_catalog(object(), entries)                 # no ModelSource needed for the gating
        panel._source = object()
        self.assertTrue(panel.select_key("o3c114"))
        self.assertTrue(panel.wait_idle(20_000))               # the stub source fails the details read; that is fine
        self.app.processEvents()
        body_set = panel.current_body_set()
        self.assertIsNotNone(body_set)
        assert body_set is not None
        self.assertEqual(body_set.keys, ("o3c114", "o3c113", "o3c115"))
        self.assertTrue(panel.export_set_button.isEnabled())
        self.assertFalse(panel.check_set_button.isEnabled())   # no folder yet
        panel.set_folder_field.setText("/tmp/body-set")
        self.assertTrue(panel.check_set_button.isEnabled())
        self.assertIn("High-detail body", panel.set_label.text())
        self.assertTrue(panel.select_key("o3c88"))
        self.assertTrue(panel.wait_idle(20_000))
        self.app.processEvents()
        self.assertIsNone(panel.current_body_set())
        self.assertFalse(panel.export_set_button.isEnabled())
        panel._source = None

    def test_set_report_text_lists_every_member_and_says_nothing_is_written(self) -> None:
        compiled_set = M.CompiledModelSet(3)
        for key, name in (("o3c114", "hi_body"), ("o3c113", "lo_body")):
            compiled_set.members.append(M.CompiledModelImport(
                key, name, 3, 0, "a" * 64, "b" * 64, "c" * 64, b"\0" * 8, 6,
                [M.ImportShapeReport(0, name + "_mesh", "vertex index lane", 8, 8, 8, 3, 0, 0, 0.75)], ["fits"]))
            compiled_set.files[key] = f"/edited/{name}.gltf"
        compiled_set.notes.append("hi_head: no edited file in the folder, left as the game shipped it")
        text = set_report_text(compiled_set)
        for phrase in ("hi_body", "lo_body", "hi_body_mesh", "3 moved", "no edited file",
                       "ONE copy of the disc", "Nothing has been written yet"):
            self.assertIn(phrase, text)

    def test_import_report_text_lists_each_mesh(self) -> None:
        compiled = M.CompiledModelImport("o1c2", "thing", 1, 2, "a" * 64, "b" * 64, "c" * 64, b"\0" * 32, 12,
                                         [M.ImportShapeReport(0, "part", "name + vertex index lane", 10, 10, 10, 4, 0, 0, 1.5, True,
                                                              1.0, 1.1, ["range widened"])],
                                         ["fits"])
        text = import_report_text(compiled)
        self.assertIn("part", text)
        self.assertIn("4 moved", text)
        self.assertIn("range widened", text)
        self.assertIn("Nothing has been written yet", text)

    @unittest.skipUnless(HAVE_DISC, "private retail extraction is absent")
    def test_catalog_filter_details_and_gating_with_a_real_disc(self) -> None:
        panel = self.panel
        panel.set_source_paths(PACK0, INVENTORY)
        self.assertTrue(panel.reload_button.isEnabled())
        panel.reload()
        self.assertTrue(panel.wait_idle(120_000))
        self.app.processEvents()
        self.assertEqual(panel.model_list.count(), 4616)
        panel.search.setText("referee")
        self.app.processEvents()
        self.assertIn("o346c109", panel.visible_keys())
        self.assertTrue(panel.select_key("o346c109"))
        self.assertTrue(panel.wait_idle(60_000))
        self.app.processEvents()
        self.assertIn("ref_high", panel.details.toPlainText())
        self.assertIn("skin: 25 joints", panel.details.toPlainText())
        self.assertTrue(panel.export_button.isEnabled())
        self.assertFalse(panel.check_button.isEnabled())       # no edited file yet
        with tempfile.TemporaryDirectory() as tmp:
            panel.export_to(Path(tmp) / "referee.gltf")
            self.assertTrue(panel.wait_idle(60_000))
            self.app.processEvents()
            self.assertTrue((Path(tmp) / "referee.gltf").is_file())
            self.assertTrue((Path(tmp) / "referee-README.txt").is_file())
            self.assertIn("Exported", panel.status_label.text())
            panel.edited_field.setText(str(Path(tmp) / "referee.gltf"))
            self.app.processEvents()
            self.assertTrue(panel.check_button.isEnabled())
            panel.compile_edited(Path(tmp) / "referee.gltf")     # unchanged: refused, nothing staged
            self.assertTrue(panel.wait_idle(120_000))
            self.app.processEvents()
        self.assertFalse(panel.write_button.isEnabled())
        self.assertFalse(panel.export_set_button.isEnabled())    # the referee is not part of a body set
        panel.search.setText("hi_body")
        self.app.processEvents()
        self.assertTrue(panel.select_key("o3c114"))
        self.assertTrue(panel.wait_idle(120_000))
        self.app.processEvents()
        body_set = panel.current_body_set()
        self.assertIsNotNone(body_set)
        assert body_set is not None
        self.assertEqual(body_set.keys, ("o3c114", "o3c113", "o3c115"))
        self.assertTrue(panel.export_set_button.isEnabled())
        panel.group_combo.setCurrentIndex(1)                     # Players
        panel.search.setText("")
        self.app.processEvents()
        self.assertTrue(0 < panel.model_list.count() < 100)

    def test_studio_offers_the_models_row_and_page(self) -> None:
        from PyQt5.QtCore import Qt
        from mod_editor.gui.studio_qt import StudioMainWindow

        window = StudioMainWindow()
        try:
            rows = [window.navigation.item(i).text().strip() for i in range(window.navigation.count())]
            self.assertIn("★ Models", rows)
            row = rows.index("★ Models")
            self.assertEqual(window.navigation.item(row).data(Qt.UserRole), "models")
            window.navigation.setCurrentRow(row)
            self.app.processEvents()
            self.assertEqual(window.page_title.text(), "Models")
            self.assertIs(window.pages.widget(row).findChildren(ModelsPanel)[0], window._models_panel)
        finally:
            for panel in window.findChildren(ModelsPanel):
                panel.wait_idle(20_000)
            self.app.processEvents()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
