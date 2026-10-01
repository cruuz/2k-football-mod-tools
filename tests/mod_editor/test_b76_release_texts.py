"""Release lab copy remains bounded; unrelated experiments retain their warnings."""
import json
import os
from pathlib import Path
import sys
import unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from PyQt5.QtWidgets import QApplication
from mod_editor.gui.build_panel_qt import BuildPanel, LAB_SCOPES

class ReleaseTexts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def test_scoped_help_and_badges_survive_source_refresh(self):
        panel=BuildPanel()
        try:
            panel.apply_state(dict(path='source.iso',container='xiso',
                                   **{k:'retail' for k in panel._boxes()}))
            for key,scope in LAB_SCOPES.items():
                with self.subTest(key=key):
                    self.assertIn(scope,panel._helpers[key].text())
                    self.assertIn(scope,panel._boxes()[key].accessibleDescription())
                    self.assertNotIn('no lab run yet',panel._helpers[key].text().lower())
                    self.assertNotEqual(panel._badges[key].text(),'EXPERIMENTAL / UNWITNESSED')
            self.assertIn('white outline star',panel.player_star_check.text())
            self.assertNotIn('gold star',panel._helpers['player_star'].text())
            for key in ('espn25_era_rules','qb_spy','screen_hooks'):
                self.assertIn('UNWITNESSED',panel._helpers[key].text())
            self.assertIn('Later venues and board passes remain offline only',panel._helpers['modern_board_kit'].text())
            self.assertIn('Away-side content',panel._helpers['historic_stock_books'].text())
        finally:panel.deleteLater();self.app.processEvents()

    def test_houston_name_and_unwitnessed_era_and_marks_scopes(self):
        self.assertEqual(json.loads((ROOT/'data/nfl2k5_board_kit/s37.json').read_text())['name'],'Reliant Stadium')
        caps={c['id']:c for c in json.loads((ROOT/'mod_editor/capabilities/registry.v1.json').read_text())['capabilities']}
        for key in ('nfl2k5.scorebug_presentation.espn_marks_2026','nfl2k5.scorebug_presentation.espn_wipes_boards_2026'):
            self.assertEqual(caps[key]['runtime']['status'],'not-tested')
        self.assertIn('102 lineups',caps['nfl2k5_xbox.position_pool_filters']['runtime']['scope'])

if __name__=='__main__':unittest.main()
