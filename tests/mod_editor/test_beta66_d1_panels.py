"""Execute the exact protected-panel handoff in memory, offscreen."""
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QMessageBox
from mod_editor.core import mod_build


def wired_module(name):
    filename = name.replace('.', '/') + '.py'
    source = (ROOT / filename).read_text()
    edits = json.loads((ROOT / 'reports/beta66_d1/panel_edits.json').read_text())[filename]
    # Work before and after integration, with no on-disk GUI mutation.
    for edit in edits:
        if edit['old'] in source:
            if source.count(edit['old']) != 1:
                raise AssertionError('ambiguous wiring insertion')
            source = source.replace(edit['old'], edit['new'])
        elif edit['new'] not in source:
            raise AssertionError('wiring context drifted')
    module = types.ModuleType(name)
    module.__file__ = str(ROOT / filename)
    module.__package__ = name.rpartition('.')[0]
    with patch.dict(sys.modules, {name: module}):
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    return module


class PlanTests(unittest.TestCase):
    def test_pairing_composes_with_read_option_and_qb_spy_and_presets_stay_clean(self):
        """Beta 66: the paired-root contract (job D2) lets separate playbooks build with the authored controls."""
        for key in ('read_option_runtime', 'qb_spy'):
            plan = mod_build.BuildPlan('missing.iso', 'out.iso', playbook_pair=True, **{key: True})
            self.assertEqual(mod_build.validate_plan(plan), [])
        for name in mod_build.PRESETS:
            plan = mod_build.apply_preset(mod_build.BuildPlan('in.iso', 'out.iso'), name)
            self.assertEqual(mod_build.validate_plan(plan), [])
            self.assertFalse(plan.playbook_pair)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.build_module = wired_module('mod_editor.gui.build_panel_qt')
        cls.game_module = wired_module('mod_editor.gui.gameplay_patches_panel_qt')

    def test_every_toggle_keeps_both_tabs_linked_and_every_playbook_row_enabled(self):
        """Beta 66: no playbook selection conflict exists; the shared gate keeps every row available."""
        from mod_editor.gui.gameplay_project_ui import GameplayBuildLink
        build = self.build_module.BuildPanel()
        game = self.game_module.GameplayPatchesPanel()
        self.addCleanup(build.deleteLater)
        self.addCleanup(game.deleteLater)
        state = {key: 'retail' for key in mod_build.PLAYBOOK_OPTION_LABELS}
        state.update(container='xiso', path='synthetic.iso')
        for p in (build, game):
            p._state = state
            p.source_field.setText('synthetic.iso')
            p.target_field.setText('out.iso')
            p._refresh()
        link = GameplayBuildLink(build, game, lambda: None)
        for origin in (build._boxes(), game.checks):
            for key in ('read_option_runtime', 'qb_spy', 'playbook_pair'):
                origin[key].click()
                for view in (build._boxes(), game.checks):
                    self.assertTrue(all(view[k].isEnabled() for k in mod_build.PLAYBOOK_OPTION_LABELS))
                    self.assertEqual(view[key].toolTip(), "")
                self.assertEqual(mod_build.validate_plan(build.plan()), [])
                origin[key].click()
        build.playbook_pair_check.setChecked(True)
        build.qb_spy_check.setChecked(True)
        self.assertFalse(getattr(build, '_playbook_blockers', ()))
        self.assertNotIn('QB spy', build.blocker() or '')
        build.playbook_pair_check.click()
        build.qb_spy_check.click()
        self.assertEqual(mod_build.validate_plan(build.plan()), [])
        del link

    def test_equipment_default_and_explicit_recolour(self):
        from types import SimpleNamespace
        cls = wired_module('mod_editor.gui.equipment_texture_import_dialog').EquipmentTextureImportDialog
        for identifier, own in (('tset:0:9:0:shoes02', True), ('tset:0:4:0:socks01', False)):
            dialog = cls(SimpleNamespace(asset_id=identifier, label='Synthetic', width=32, height=32))
            self.assertEqual(dialog.independent, own)
            self.assertEqual(dialog.game_size.isEnabled(), own)
            if own:
                dialog.own_texture.click()
                self.assertFalse(dialog.independent)
                self.assertFalse(dialog.game_size.isEnabled())
            dialog.deleteLater()

    def test_roster_open_warning_and_repair_offer(self):
        from tests.mod_editor.test_nfl2k5_college_check import corrupt
        from tests.mod_editor.test_nfl2k5_roster_records import synthetic_body
        from mod_editor.core import nfl2k5_roster_records as rr
        module = wired_module('mod_editor.gui.roster_editor_panel_qt')
        panel = module.RosterEditorPanel()
        self.addCleanup(panel.deleteLater)
        bad, _ = corrupt(synthetic_body(), 'outside')
        bad, _ = corrupt(bad, 'null', player=1)
        document = rr.RosterDocument(bad, base=rr.find_block_base(bad))
        panel.load_document(document)
        self.app.processEvents()
        # The offer is a non-blocking question box parented to the panel (no nested event loop).
        prompts = [box for box in panel.findChildren(module.QMessageBox) if 'Open Check my rosters' in box.text()]
        self.assertEqual(len(prompts), 1)
        self.assertIn('2 players have a missing/invalid college', prompts[0].text())
        with patch.object(panel, 'open_college_check') as opened:
            prompts[0].button(QMessageBox.No).click()
            self.app.processEvents()
            self.assertFalse(opened.called)
        self.assertIn('2 players have a missing/invalid college', panel.status_label.text())
        self.assertIsNotNone(panel.college_check_session())


if __name__ == '__main__':
    unittest.main()
