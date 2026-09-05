"""★ Rosters after the UX pass (E5): Finn's layout, honest words, explicit saves.

* the grid calls the overall an estimate (the editor computes its own);
* the position scheme stays visible as "Position names: …" while the override selector
  sits under Change position scheme;
* the contract line reads as money, the height / weight / contract cards carry units;
* the Global Attribute Editor forgets a preview the moment a setting changes and always
  recalculates before Apply;
* an exported roster-edits file is a snapshot: a later edit marks it stale.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests", ROOT / "tests" / "mod_editor"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from PyQt5.QtWidgets import QApplication  # noqa: E402

from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402
from mod_editor.gui.roster_editor_panel_qt import GlobalEditDialog, RosterEditorPanel  # noqa: E402
from test_roster_editor_panel_qt import synthetic_body  # noqa: E402


class RosterWordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.panel = RosterEditorPanel()
        self.panel.load_document(rr.load_body(synthetic_body()), label="synthetic")
        self.app.processEvents()

    def tearDown(self) -> None:
        self.panel.deleteLater()
        self.app.processEvents()

    def test_the_grid_and_the_header_say_what_they_show(self) -> None:
        panel = self.panel
        self.assertEqual(panel.player_table.horizontalHeaderItem(4).text(), "Est. OVR")
        self.assertIn("estimate", panel.player_table.horizontalHeaderItem(4).toolTip())
        self.assertTrue(panel.scheme_label.text().startswith("Position names:"), panel.scheme_label.text())
        self.assertFalse(panel.scheme_details.is_expanded())
        self.assertIs(panel.scheme_combo.parentWidget().parentWidget(), panel.scheme_details)
        panel.team_list.setCurrentRow(0)
        panel.player_table.selectRow(0)
        self.app.processEvents()
        self.assertTrue(panel.header_contract.text().startswith("Contract:"))
        self.assertIn("M total", panel.header_contract.text())
        self.assertIn("cut penalty", panel.header_contract.text())
        self.assertNotIn("(code", panel.header_profile.text())
        self.assertIn("key ratings", panel.header_profile.text())
        self.assertIn("age in Sep 2004", panel.header_stats.text())
        self.assertEqual(panel.cards["height"].caption.text(), "Height (inches)")
        self.assertEqual(panel.cards["weight"].caption.text(), "Weight (lb)")
        self.assertTrue(panel.cards["contract_value"].caption.text().startswith("Contract value ($10,000 units)"))
        self.assertEqual(panel.edited_label.text(), "No roster edits yet")

    def test_the_global_editor_forgets_a_preview_when_a_setting_changes(self) -> None:
        dialog = GlobalEditDialog(self.panel, self.panel)
        try:
            self.assertEqual(dialog.large_values.text(), "Allow ratings above 99 (up to 127)")
            self.assertEqual(dialog.scope_label.text(), "Scope: all players")
            dialog.value.setValue(5)
            rows = dialog.refresh_preview()
            self.assertTrue(rows)
            self.assertIn("would change", dialog.count_label.text())
            dialog.attribute.setCurrentIndex(dialog.attribute.currentIndex() + 1)
            self.assertEqual(dialog.preview_rows, [], "a changed setting must drop the old preview")
            self.assertIn("press Show affected players again", dialog.count_label.text())
            dialog.current_team_only.setChecked(True)
            self.assertTrue(dialog.scope_label.text().startswith("Scope: "))
            self.assertNotEqual(dialog.scope_label.text(), "Scope: all players")
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_an_exported_snapshot_goes_stale_after_the_next_edit(self) -> None:
        panel = self.panel
        stale: list[bool] = []
        panel.roster_edits_stale.connect(lambda: stale.append(True))
        panel.team_list.setCurrentRow(0)
        panel.player_table.selectRow(0)
        self.app.processEvents()
        player = panel.selected_player()
        self.assertIsNotNone(player)
        panel._card_changed("speed", 55)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edits.json"
            panel.save_edits_to(path)
            self.assertIn("Export again after further changes", panel.status_label.text())
            self.assertEqual(stale, [])
            panel._card_changed("speed", 56)
            self.assertEqual(stale, [True])
            self.assertIn("exported", panel.status_label.text())

    def test_the_checks_page_names_the_check_not_a_tag(self) -> None:
        panel = self.panel
        findings = panel.run_validation()
        report = panel.report.toPlainText()
        self.assertNotIn("[WARNING]", report)
        self.assertNotIn("[INFO]", report)
        if findings:
            self.assertTrue(any(report.startswith(word) for word in ("Editor check", "Error", "Info", "Nothing")), report[:80])


if __name__ == "__main__":
    unittest.main()
