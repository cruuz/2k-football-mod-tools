"""Offscreen designer controls produce the same verified core plans."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace
import unittest

from PyQt5.QtWidgets import QApplication
from test_apf_play_designer import synthetic, synthetic_cpu, play_request
from mod_editor.core.apf2k8_play_codec import Book
from mod_editor.core.apf2k8_play_designer import compile_design, empty_plan
from mod_editor.core.apf2k8_splb_writer import parse_book
from mod_editor.apf_studio.play_designer_qt import PlayDesignDialog, FormationDesignDialog, CpuCallDialog, PlayDesignerPanel


class DesignerQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.source = synthetic()
        self.book = Book.from_bytes(self.source)

    def test_play_fields_produce_a_private_chain(self):
        dialog = PlayDesignDialog(self.book, 4)
        self.addCleanup(dialog.close)
        dialog.slot.setCurrentIndex(1)
        dialog.node.setCurrentIndex(1)
        dialog.field.setCurrentIndex(dialog.field.findData("distance_ft"))
        dialog.value.setValue(30)
        dialog._add()
        plan = empty_plan(self.source)
        plan["plays"] = [dialog.request()]
        after = Book.from_bytes(compile_design(self.source, plan).replacement)
        self.assertEqual(after.chain(4, 1)[1].operands[2], 30 * 30.48)
        self.assertEqual(after.chain(0, 1), self.book.chain(0, 1))

    def test_formation_edits_all_alignment_variants(self):
        dialog = FormationDesignDialog(self.book, 2)
        self.addCleanup(dialog.close)
        dialog.table.cellWidget(0, 1).setValue(-500)
        plan = empty_plan(self.source)
        plan["formations"] = [dialog.request()]
        after = Book.from_bytes(compile_design(self.source, plan).replacement)
        self.assertEqual(after.formations[2].slots[0].y, (-500, 0, 0))

    def test_cpu_dialog_uses_named_book_record_indices(self):
        dialog = CpuCallDialog(self.book, {259: parse_book(synthetic_cpu(), 259)})
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.request()["outer"], 259)
        self.assertEqual(dialog.request()["record"], 0)
        self.assertIsNone(dialog.request()["donor_record"])

    def test_panel_disables_without_source_and_emits_after_stage(self):
        facade = SimpleNamespace(source_ready=False)
        panel = PlayDesignerPanel(facade, lambda *a, **k: None)
        self.addCleanup(panel.close)
        self.assertFalse(panel.play_button.isEnabled())
        panel.set_data((self.source, None, {259: parse_book(synthetic_cpu(), 259)}))
        self.assertTrue(panel.play_button.isEnabled())
        self.assertFalse(panel.stage_button.isEnabled())
        events = []
        panel.modifiedChanged.connect(lambda: events.append(True))
        panel._staged({"resources": [{"outer": 180, "free_bytes": 20}]})
        self.assertEqual(events, [True])
        self.assertIn("UNWITNESSED", panel.status.text())

    def test_refresh_preserves_unstaged_draft(self):
        tasks = []
        panel = PlayDesignerPanel(SimpleNamespace(source_ready=True), lambda *a: tasks.append(a))
        self.addCleanup(panel.close)
        panel.set_data((self.source, None, {}))
        draft = empty_plan(self.source)
        draft["plays"] = [play_request("append", 4, 0, "Draft")]
        self.assertTrue(panel._accept(draft))
        self.assertTrue(panel.stage_button.isEnabled())
        panel.refresh()
        self.assertEqual(tasks, [])
        self.assertEqual(panel.draft, draft)


if __name__ == "__main__":
    unittest.main()
