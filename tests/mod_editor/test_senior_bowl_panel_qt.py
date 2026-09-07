"""Standalone offscreen configuration, sorted identity and project checks."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_senior_bowl as bowl
from tests.nfl2k5_senior_bowl_fixture import prospects

HAVE_QT = importlib.util.find_spec("PyQt5") is not None


@unittest.skipUnless(HAVE_QT, "PyQt5 is absent; offscreen Senior Bowl panel tests unavailable")
class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.gui.senior_bowl_panel_qt import SeniorBowlPanel
        self.panel = SeniorBowlPanel()

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()
        self.app.processEvents()

    def test_defaults_preview_and_simulate_stays_disabled(self):
        p = self.panel
        p.set_players(prospects())
        self.assertEqual([table.rowCount() for table in p.tables], [53, 53, len(prospects())])
        self.assertFalse(p.options()["senior_bowl"])
        self.assertFalse(p.simulate_button.isEnabled())
        self.assertIn("In-game event unavailable", p.summary.text())
        self.assertEqual(p.settings(), bowl.Settings())

    def test_sort_select_resolves_saved_primary_identity(self):
        from PyQt5.QtCore import Qt
        p = self.panel
        p.set_players(prospects())
        table = p.tables[0]
        for col in (0, 1, 2):
            table.sortItems(col, Qt.DescendingOrder)
            table.selectRow(7)
            key = p.selected_player_index(0)
            self.assertEqual(key, table.item(7, 2).data(Qt.DisplayRole))
            self.assertEqual(table.item(7, 0).text(), next(row.name for row in prospects() if row.index == key))

    def test_settings_roundtrip_and_activation_refusal_before_changes(self):
        p = self.panel
        options = {"senior_bowl": False, "senior_bowl_settings": bowl.Settings(scheme="edge", away=bowl.Kit(51,"A"), home=bowl.Kit(50,"H")).to_dict(), "senior_bowl_seed": 42}
        p.set_options(options)
        self.assertEqual(p.options(), options)
        with self.assertRaises(ValueError):
            p.set_options({**options, "senior_bowl": True})
        self.assertEqual(p.options(), options)

    def test_missing_source_project_load_preserves_choices_and_clears_old_rosters(self):
        p = self.panel
        p.set_players(prospects())
        with tempfile.TemporaryDirectory() as temp:
            source = str(Path(temp) / "missing-SAVEGAME.DAT")
            path = Path(temp) / "senior.2k5senior"
            settings = bowl.Settings(scheme="one_pool")
            bowl.atomic_write(path, bowl.project_bytes(settings, 51, source))
            p.load_project(path)
        self.assertEqual(p.settings(), settings)
        self.assertEqual(p.seed.value(), 51)
        self.assertEqual([t.rowCount() for t in p.tables], [0, 0, 0])
        self.assertIn("source save is missing", p.summary.text())

    def test_shortage_keeps_full_class_and_explains_missing_specialist(self):
        p = self.panel
        rows = tuple(x for x in prospects() if x.position != 2)
        p.set_players(rows)
        self.assertEqual([t.rowCount() for t in p.tables], [0, 0, len(rows)])
        self.assertIn("P: need 2, found 0", p.summary.text())


if __name__ == "__main__":
    unittest.main()
