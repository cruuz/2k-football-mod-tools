"""New page controls, project choices and stale worker replies, offscreen."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PyQt5.QtWidgets import QApplication
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.gameplay_patches_panel_qt import GameplayPatchesPanel, PATCHES
from mod_editor.gui import beta62_options as ui
from mod_editor.core import mod_build, nfl2k5_build_settings as saved


class IntegrationQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.source=Path(self.temp.name)/'source.iso'
        self.source.write_bytes(b'fixture')
        self.panel=BuildPanel()
        self.state={'path':str(self.source),'container':'xiso',**{k:'retail' for k in self.panel._boxes()},
                    'momentum_settings':{'status':'retail'}}
        self.panel.apply_state(self.state)
        self.panel.target_field.setText(str(Path(self.temp.name)/'target.iso'))

    def tearDown(self):
        self.panel._hires_budget_timer.stop()
        self.panel.deleteLater();self.app.processEvents();self.temp.cleanup()

    def test_offline_events_stay_disabled_in_both_panels(self):
        other=GameplayPatchesPanel();other.apply_state(self.state)
        for key in ui.UNAVAILABLE:
            self.assertFalse(self.panel._boxes()[key].isEnabled())
            self.assertFalse(other.checks[key].isEnabled())
        other.deleteLater()

    def test_controls_roundtrip_typed_choices(self):
        state={'momentum_collisions':True,'momentum_collision_level':37,'guardian_overlay':True,
               'guardian_everyone_practice':False,'created_teams_extra':2,'my_career_setup':'prepared.json',
               'my_career':True,'senior_bowl_seed':17,'hires_families':['helmets','jerseys']}
        self.panel.restore_project_build_settings(state)
        result=self.panel.project_build_settings()
        for key,value in state.items():self.assertEqual(result[key],value,key)
        self.assertFalse(self.panel.guardian_cap_check.isChecked())
        self.assertEqual(self.panel.plan().created_teams_extra,2)
        self.assertEqual(self.panel.plan().momentum,0)

    def test_prepared_career_path_does_not_select_the_patch(self):
        from types import SimpleNamespace
        from mod_editor.gui.studio_qt import StudioMainWindow
        host=SimpleNamespace(_build_panel=self.panel, _ensure_workspace=lambda index: None, navigation=SimpleNamespace(count=lambda: 1),  # beta 66: lazy pages
            _capture_music_build_settings=lambda:None, _mark_workspace_changed=lambda:None)
        self.panel.my_career_check.setChecked(False)
        StudioMainWindow._my_career_setup_ready(host,'paired/MyCareer.json')
        self.assertEqual(self.panel.my_career_setup_field.text(),'paired/MyCareer.json')
        self.assertFalse(self.panel.my_career_check.isChecked())

    def test_scorebar_folder_from_the_studio_page_fills_the_field_without_ticking_the_option(self):
        from types import SimpleNamespace
        from mod_editor.gui.studio_qt import StudioMainWindow
        host=SimpleNamespace(_build_panel=self.panel, _set_status=lambda *_: None, _ensure_workspace=lambda index: None, navigation=SimpleNamespace(count=lambda: 1),
            _capture_music_build_settings=lambda:None, _mark_workspace_changed=lambda:None)
        self.panel.scorebug_check.setChecked(False)
        StudioMainWindow._scorebar_folder_chosen(host,'/tmp/my scorebar')
        self.assertEqual(self.panel.scorebug_folder_field.text(),'/tmp/my scorebar')
        self.assertFalse(self.panel.scorebug_check.isChecked())

    def test_collision_only_source_locks_both_halves_and_shows_installed_level(self):
        state={**self.state,'momentum_collisions':'applied','momentum':'retail',
               'momentum_settings':{'status':'applied','momentum':0,'momentum_contact':False,
                                    'momentum_collisions':True,'momentum_collision_level':37}}
        self.panel.apply_state(state)
        for key in ('momentum','momentum_contact','momentum_collisions'):
            self.assertFalse(self.panel._boxes()[key].isEnabled())
        self.assertEqual(self.panel.momentum_collision_level.currentData(),37)
        self.assertFalse(self.panel.momentum_level.isEnabled())

    def test_late_hires_success_cannot_clear_new_folder_failure(self):
        self.panel.hires_pack_check.setChecked(True)
        self.panel.hires_folder_field.setText('old');old=self.panel._hires_identity()
        self.panel.hires_folder_field.setText('new');new=self.panel._hires_identity()
        self.panel._hires_budget_timer.stop()
        reason='Hi-res allocations exceed the ceiling by 123 bytes.'
        self.panel._hires_budget_done(new,None,reason)
        self.panel._hires_budget_done(old,{'message':'under ceiling','modeled_delta_bytes':5})
        self.assertEqual(self.panel.blocker(),reason)
        self.assertFalse(self.panel.build_button.isEnabled())
        self.panel._hires_budget_done(new,{'message':'Whole-game memory fit is unproved.','modeled_delta_bytes':5})
        self.assertIn('unproved',self.panel.hires_budget_label.text())

    def test_all_new_patch_help_is_actionable_and_short(self):
        for key,caption,help in ui.OPTIONS:
            self.assertLessEqual(len(caption),60)
            self.assertIn('Retail',help);self.assertIn('Patch',help)
            self.assertIn(key,dict((key,label) for key,label,_ in PATCHES))

    def test_guardian_bulk_undo_restores_exact_records_and_checkbox(self):
        from mod_editor.gui.roster_editor_panel_qt import RosterEditorPanel
        from mod_editor.core import nfl2k5_roster_records as rr
        from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
        panel=RosterEditorPanel()
        self.addCleanup(panel.deleteLater)
        panel.load_document(rr.load_body(synthetic_body()))
        players=panel.document.players[:3]
        for player in players:player.record.guardian_cap=False
        before=[player.record.encode() for player in players]
        self.assertEqual(panel.set_guardian_caps(players,True),3)
        after=[player.record.encode() for player in players]
        for old,new in zip(before,after):
            expected=bytearray(old);expected[0x53]|=0x20
            self.assertEqual(new,bytes(expected))
        self.assertTrue(panel.guardian_cap_check.isChecked())
        panel.undo()
        self.assertEqual([player.record.encode() for player in players],before)
        self.assertFalse(panel.guardian_cap_check.isChecked())
        panel.redo()
        self.assertEqual([player.record.encode() for player in players],after)


if __name__=='__main__':unittest.main()
