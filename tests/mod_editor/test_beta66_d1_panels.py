"""Exercise the integrated protected panels offscreen, including later wording."""
import importlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QMessageBox
from mod_editor.core import mod_build


def wired_module(name):
    # The handoff is installed. Exercise its real behavior without replaying
    # obsolete source-text hunks over later model, equipment and polish changes.
    return importlib.import_module(name)


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
        # The beta-66 handoff has shipped and beta 68 adds catalog-backed scope
        # and own socks. Exercise the live dialog with complete reviewed rows.
        from mod_editor.gui.equipment_texture_import_dialog import EquipmentTextureImportDialog
        from mod_editor.core.nfl2k5_uniform_equipment_writer import load_targets
        targets = load_targets()[0]
        for identifier, own in (('tset:3613:8:0:shoes01', True),
                                ('tset:3613:4:0:socks00', True),
                                ('tset:3613:5:0:elbowpad01', False)):
            target = targets[identifier]
            dialog = EquipmentTextureImportDialog(SimpleNamespace(
                asset_id=identifier, label=target.name, width=target.width, height=target.height))
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
        # The offer is an inline banner inside the panel: no dialog, no timer, no nested event loop
        # (a message box shown from the load path crashes under the offscreen platform on Windows).
        banner = panel._college_banner
        self.assertFalse(banner.isHidden())
        self.assertIn('2 players have a missing/invalid college', panel._college_banner_label.text())
        self.assertIn('Open Check my rosters', panel._college_banner_label.text())
        with patch.object(panel, 'open_college_check') as opened:
            panel._college_banner_open.click()
            self.app.processEvents()
            self.assertTrue(opened.called)
        later = next(b for b in banner.findChildren(module.QPushButton) if b.text() == 'Later')
        later.click()
        self.app.processEvents()
        self.assertTrue(banner.isHidden())
        self.assertIn('2 players have a missing/invalid college', panel.status_label.text())
        self.assertIsNotNone(panel.college_check_session())
        # A clean document hides the offer again.
        panel.load_document(rr.RosterDocument(synthetic_body(), base=rr.find_block_base(synthetic_body())))
        self.app.processEvents()
        self.assertTrue(banner.isHidden())


if __name__ == '__main__':
    unittest.main()
