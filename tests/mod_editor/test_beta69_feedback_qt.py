"""Failure and completion copy report what actually happened, including no-op builds."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['MOD_STUDIO_NO_UPDATE_CHECK'] = '1'
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PyQt5.QtWidgets import QApplication, QMessageBox
from mod_editor.gui.build_panel_qt import BuildPanel
from mod_editor.gui.update_ui import UpdateBanner, report_manual_check
from mod_editor.core.update_check import UpdateStatus
from mod_editor.apf_studio.gui import ApfStudioMainWindow

class FeedbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_disc_ready_names_selection_and_preserves_fit_warning(self):
        panel = BuildPanel(available={})
        panel._requested_build_labels = ['Fix Catching & Interception sliders', 'Project artwork']
        receipt = {'target': 'new.iso', 'steps': [{'step': 'xbe'}, {'step': 'visual_project',
                    'kept_retail': [{'message': 'Home jersey digits stayed original because the art did not fit.'}]}],
                   'outcome': {'status': 'changed', 'message': 'The output differs from the source.'}}
        with patch.object(QMessageBox, 'information') as dialog, patch('mod_editor.gui.build_panel_qt.tt.is_disc_image', return_value=True):
            panel._done(receipt)
        title, body = dialog.call_args.args[1:3]
        self.assertEqual(title, 'Disc ready')
        self.assertIn('Fix Catching & Interception sliders', body)
        self.assertIn('digits stayed original', body)
        self.assertNotIn('Steps checked:', body)
        self.assertIn('Play latest disc in xemu', body)
        panel.copy_summary_button.click()
        self.assertIn('beta-75', self.app.clipboard().text())
        self.assertIn('Project artwork', self.app.clipboard().text())
        panel.deleteLater()

    def test_unchanged_receipt_does_not_claim_changed_disc(self):
        panel = BuildPanel(available={})
        with patch.object(QMessageBox, 'information') as dialog:
            panel._done({'target': 'new.iso', 'steps': [], 'outcome': {'status': 'unchanged',
                'message': 'No changes were written. The output is an unchanged copy of the source.'}})
        self.assertEqual(dialog.call_args.args[1], 'No changes written')
        self.assertIn('unchanged copy', panel._last_build_summary)
        panel.deleteLater()

    def test_first_error_is_available_in_copyable_summary(self):
        panel = BuildPanel(available={})
        panel._requested_build_summary = 'Source: original.iso\nChanges: shoe artwork'
        with patch.object(QMessageBox, 'exec_', return_value=QMessageBox.Ok):
            panel._failed('NFL2K5_BUILD_PHASE validate_source seconds=0.5\nNfl2k5BuildError: Shoe art could not fit.')
        panel.copy_summary_button.click()
        text = self.app.clipboard().text()
        self.assertIn('Source: original.iso', text)
        self.assertIn('First error: Shoe art could not fit.', text)
        self.assertNotIn('BUILD_PHASE', text)
        self.assertNotIn('Nfl2k5BuildError:', text)
        panel.deleteLater()

    def test_apf_receipt_distinguishes_art_and_book_only_builds(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'receipt.json'
            manifest.write_text(json.dumps({'edits': [{'kind': 'helmet_crest_design'}]}))
            receipt = SimpleNamespace(manifest=manifest, modified_assets=('crest',), teams_now_own_books=())
            text = ApfStudioMainWindow._build_edit_detail(receipt)
            self.assertIn('artwork and appearance edits', text)
            self.assertNotIn('CPU Play Calling', text)
            manifest.write_text(json.dumps({'edits': [], 'playcalling': {'changed': True}}))
            receipt.modified_assets = ()
            text = ApfStudioMainWindow._build_edit_detail(receipt)
            self.assertIn('CPU Play Calling edits', text)
            self.assertNotIn('plain copy', text)

    def test_update_failure_and_browser_failure_have_a_next_step(self):
        banner = UpdateBanner()
        banner._on_done(None, 'SelfUpdateError: Download was interrupted.')
        self.assertIn('Download was interrupted.', banner.message.text())
        self.assertIn('Setup.exe', banner.message.text())
        self.assertNotIn('SelfUpdateError:', banner.message.text())
        banner._status = UpdateStatus(True, 'beta-69', 'beta-70')
        with patch('mod_editor.gui.update_ui.QDesktopServices.openUrl', return_value=False):
            banner._open_downloads()
        self.assertIn('Could not open your browser', banner.message.text())
        self.assertIn('https://github.com/', banner.message.text())
        banner.deleteLater()

if __name__ == '__main__':
    unittest.main()
