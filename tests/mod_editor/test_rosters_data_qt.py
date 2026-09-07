"""Standalone offscreen tests of style controls and explicit age review/save/undo."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PyQt5.QtWidgets import QApplication, QLabel
    from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel, AgeShiftDialog
except ImportError:
    QApplication = None
from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_roster_ages as ages
from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
from tests.mod_editor.test_nfl2k5_franchise_save import synthetic_franchise


@unittest.skipUnless(QApplication is not None, "PyQt5 is unavailable; offscreen controls require Qt")
class ControlsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.panel = RosterEditorPanel()
        self.doc = rr.RosterDocument(synthetic_body())
        self.panel.load_document(self.doc)

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_named_controls_visible_parity_and_raw_power_undo(self):
        player = self.doc.players[0]
        player.record.set("power_run_style", 38)
        player.record.set("scramble", 52)
        self.panel.select_player(player)
        text = " ".join(label.text() for label in self.panel.findChildren(QLabel))
        self.assertIn("odd = scrambler", text)
        self.assertIn("EXPERIMENTAL / UNWITNESSED", text)
        self.assertEqual([b.text() for b in self.panel.cards["power_run_style_bucket"].segments],
                         ["Finesse", "Balanced", "Power"])
        before = player.record.encode()
        self.panel.cards["power_run_style_bucket"].segments[2].click()
        self.assertEqual(player.record.values["power_run_style"], 99)
        self.panel.undo()
        self.assertEqual(player.record.encode(), before)
        self.panel.redo()
        self.panel.cards["throw_style"].segments[1].click()
        self.assertEqual(player.record.values["scramble"], 53)
        self.panel.cards["scramble"].spin.setValue(90)
        self.assertEqual(player.record.values["scramble"], 91)
        self.assertEqual(self.panel.cards["scramble"].spin.value(), 91)
        self.panel.undo()
        self.assertEqual(player.record.values["scramble"], 53)
        # An attempted adjacent numeric value rounds back to the actual parity.
        self.panel.cards["scramble"].spin.setValue(52)
        self.assertEqual(self.panel.cards["scramble"].spin.value(), 53)
        self.panel.undo()
        self.assertEqual(player.record.values["scramble"], 52)

    def test_kicking_presets_csv_undo_and_validation(self):
        player = self.doc.players[0]
        self.panel.select_player(player)
        before = self.doc.to_body()
        self.panel.cards["kicking_style"]._presets[2].click()
        self.assertEqual(player.record.values["kicking_style"], 99)
        csv = self.panel.export_csv_text(everything=True)
        other = rr.RosterDocument(synthetic_body())
        rr.import_csv(other, csv)
        self.assertEqual(other.to_body(), self.doc.to_body())
        self.panel.undo()
        self.assertEqual(self.doc.to_body(), before)
        receipt = self.panel.import_csv_text("pool,index,scramble,kicking_style,power_run_style\nprimary,0,97,1,38\n")
        self.assertEqual(receipt["changed"], 1)
        self.panel.undo()
        self.assertEqual(self.doc.to_body(), before)
        self.panel.redo()
        self.assertEqual(player.record.values["power_run_style"], 38)

    def test_global_power_undo_retains_noncanonical_values(self):
        for p in self.doc.players:
            p.record.set("power_run_style", 38)
        before = self.doc.to_body()
        plan = self.panel.global_edit_preview(attribute="power_run_style_bucket", mode="equal", value=2)
        self.panel.apply_global_edit(plan, "power_run_style_bucket")
        self.panel.undo()
        self.assertEqual(self.doc.to_body(), before)

    def test_age_dialog_preview_cancel_apply_undo_redo_receipt_and_header(self):
        before = self.doc.to_body()
        dialog = AgeShiftDialog(self.panel)
        self.assertEqual(dialog.target_year.value(), 2026)
        self.assertEqual(dialog.source_year.value(), 2004)
        self.assertTrue(dialog.apply_button.isEnabled())
        self.assertEqual(self.doc.to_body(), before)
        dialog.reject()
        self.assertEqual(self.doc.to_body(), before)
        dialog.deleteLater()
        dialog = AgeShiftDialog(self.panel)
        dialog.shown_only.setChecked(True)
        self.assertEqual(dialog.plan["changed"], 3)
        dialog.apply_button.click()
        after = self.doc.to_body()
        self.assertNotEqual(after, before)
        self.assertIn("age on Sep 1, 2026", self.panel.header_stats.text())
        self.assertIn("1976-03-24 -> 1998-03-24", self.panel.report.toPlainText())
        receipt_path = self.root / "receipt.json"
        action = next(a for a in self.panel.passes_button.menu().actions()
                      if a.text() == "Export age shift receipt...")
        with patch("mod_editor.gui.roster_editor_panel_qt.QFileDialog.getSaveFileName",
                   return_value=(str(receipt_path), "JSON (*.json)")):
            action.trigger()
        self.assertEqual(len(json.loads(receipt_path.read_text())["receipts"][0]["changes"]), 3)
        self.panel.undo()
        self.assertEqual(self.doc.to_body(), before)
        self.assertIsNone(self.doc.reference_year)
        self.assertEqual(self.panel.age_shift_receipts, [])
        self.panel.redo()
        self.assertEqual(self.doc.to_body(), after)
        repeated = AgeShiftDialog(self.panel)
        self.assertEqual(repeated.source_year.value(), 2026)
        self.assertFalse(repeated.apply_button.isEnabled())
        repeated.deleteLater()
        dialog.deleteLater()

    def test_stale_preview_refuses_without_partial_edits(self):
        dialog = AgeShiftDialog(self.panel)
        self.panel.set_field(self.doc.players[0], "speed", 25)
        before = self.doc.to_body()
        dialog.apply_button.click()
        self.assertIn("stale", dialog.report.toPlainText())
        self.assertEqual(self.doc.to_body(), before)
        dialog.deleteLater()

    def test_explicit_signed_save_copy_keeps_source_and_franchise_calendar(self):
        source = self.root / "source"
        source.mkdir()
        raw = synthetic_franchise(year_field=0)
        (source / "SAVEGAME.DAT").write_bytes(raw)
        (source / "EXTRA").write_bytes(rr.sign_save(raw))
        self.assertTrue(self.panel.load_save(source))
        doc = self.panel.document
        before = doc.to_body()
        plan = ages.preview(doc, 2004, 2026)
        self.panel.apply_age_shift(plan)
        after = doc.to_body()
        self.assertEqual((source / "SAVEGAME.DAT").read_bytes(), raw)
        self.panel.write_copy_to(self.root / "shifted.zip")
        reopened = rr.load_save(self.root / "shifted.zip", base_year=2026)
        self.assertEqual(reopened.to_body(), after)
        self.assertEqual(reopened.container.savegame, after)
        self.assertEqual((source / "SAVEGAME.DAT").read_bytes(), raw)
        self.panel.undo()
        self.assertEqual(doc.to_body(), before)
        self.panel.redo()
        self.assertEqual(doc.to_body(), after)


if __name__ == "__main__":
    unittest.main()
