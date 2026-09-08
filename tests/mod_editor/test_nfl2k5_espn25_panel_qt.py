"""Standalone offscreen panel tests; no display or game used."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests'):
    sys.path.insert(0, str(path))
from espn25_fixture import fixtures, draft
from mod_editor.core import nfl2k5_espn25_scenarios as e
try:
    from PyQt5 import QtCore, QtWidgets
    from mod_editor.gui.espn25_panel_qt import Espn25Panel
    QT_ERROR = None
except ImportError as exc:
    QT_ERROR = str(exc)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if QT_ERROR:
            raise unittest.SkipTest('PyQt5 unavailable for offscreen panel: ' + QT_ERROR)
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.catalog = fixtures()

    def setUp(self):
        self.panel = Espn25Panel()
        self.panel.set_catalog(self.catalog)
        self.addCleanup(self.panel.close)
        self.addCleanup(self.panel.deleteLater)

    def test_selection_shared_roster_and_existing_model(self):
        p = self.panel
        self.assertEqual(p.moments.count(), 25)
        self.assertEqual(p.table.rowCount(), 53)
        self.assertIn('Shared by moments: 1 away, 1 home', p.binding_label.text())
        self.assertEqual(p.table.editTriggers(), QtWidgets.QAbstractItemView.NoEditTriggers)
        self.assertFalse(p.table.item(0, 0).flags() & QtCore.Qt.ItemIsEditable)
        self.assertEqual(p.csv_text(), self.catalog.export_csv(0, 'away'))

    def test_import_staging_shared_selection_and_signal(self):
        p = self.panel
        with self.assertRaisesRegex(e.Espn25Error, 'acknowledge'):
            p.import_csv_text('pool,index,jersey\nprimary,0,12\n')
        p.shared.setChecked(True)
        p.import_csv_text('pool,index,jersey\nprimary,0,12\n')
        p.import_csv_text('pool,index,speed\nprimary,0,91\n')
        p.sides.setCurrentIndex(1)
        self.assertEqual(p.table.item(0, e.CSV_COLUMNS.index('jersey')).text(), '12')
        self.assertEqual(p.table.item(0, e.CSV_COLUMNS.index('speed')).text(), '91')
        received = []; p.plan_ready.connect(received.append)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / 'plan.json'
            plan = p.save_plan(path)
            self.assertEqual(e.read_json(path), plan)
            self.assertEqual(received[0]['path'], str(path))
            self.assertFalse(e.resolve_plan(self.catalog, plan)[1])
        self.assertEqual(self.catalog.roster_document(0, 'away').players[0].record.values['jersey'], 0)

    def test_invalid_table_cell_keeps_source_and_refuses_plan(self):
        p = self.panel; p.shared.setChecked(True)
        p.table.item(0, e.CSV_COLUMNS.index('jersey')).setText('999')
        with self.assertRaises(e.Espn25Error): p.make_plan()
        self.assertEqual(self.catalog.roster_document(0, 'away').players[0].record.values['jersey'], 0)

    def test_scenario_json_and_research_refusal(self):
        import json
        p = self.panel
        p.scenario_json.setPlainText(json.dumps({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'setup': {'home_score': 21}}]}))
        self.assertFalse(e.resolve_plan(self.catalog, p.make_plan())[1])
        p.scenario_json.setPlainText(json.dumps(draft(self.catalog)))
        with self.assertRaisesRegex(e.Espn25Error, '30 moments'): p.make_plan()
        p.scenario_json.setPlainText('{"schema":1,"schema":2}')
        with self.assertRaisesRegex(e.Espn25Error, 'duplicate'): p.make_plan()

    def test_team_change_under_roster_edit_refuses(self):
        import json
        p = self.panel; p.shared.setChecked(True)
        p.import_csv_text('pool,index,jersey\nprimary,0,12\n')
        p.scenario_json.setPlainText(json.dumps({'schema': e.SCHEMA, 'moments': [{'moment': 0, 'teams': {'away': {'selector': 'team01', 'year': 1951}}}]}))
        with self.assertRaisesRegex(e.Espn25Error, 'selection changed'): p.make_plan()


if __name__ == '__main__':
    unittest.main()
