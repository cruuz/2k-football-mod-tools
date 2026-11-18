"""Protect an existing coach through Studio's ordinary signed-copy editor."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_save_writer as writer
from tests import nfl2k5_save_writer_test as fixtures


class OwnerFiringSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_a_settings_file_or_out_of_range_setting_is_refused(self):
        original = bytes(writer.SETTINGS_BLOCK_SIZE)
        settings = bytearray(original)
        with self.assertRaisesRegex(writer.SaveWriterError, 'franchise save'):
            writer.apply_option_edits(settings, {'owner_firing': 0})
        self.assertEqual(settings, original)
        franchise = bytearray(fixtures._franchise_save())
        old = bytes(franchise)
        for invalid in (-1, 3, True, '0'):
            with self.subTest(invalid=invalid), self.assertRaises(writer.SaveWriterError):
                writer.apply_option_edits(franchise, {'owner_firing': invalid})
            self.assertEqual(franchise, old)

    def test_off_is_written_only_when_the_player_chooses_it_on_a_franchise(self):
        from PyQt5.QtTest import QTest
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        from mod_editor.gui.save_panel_qt import SavePanel
        panel = SavePanel()
        self.addCleanup(panel.deleteLater)
        def wait():
            for _ in range(150):
                self.app.processEvents()
                if not panel.operation_in_progress:
                    return
                QTest.qWait(20)
            self.fail('save operation did not complete')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / 'default.xbe'
            game.write_bytes(fixtures._build_synth_xbe())
            source = root / 'Franchise1' / 'SAVEGAME.DAT'
            source.parent.mkdir()
            payload = bytearray(fixtures._franchise_save())
            at = writer.OWNER_FIRING_VA - writer.OPTION_BLOCK_VA
            struct.pack_into('<I', payload, at, 2)
            source.write_bytes(payload)
            source_extra = source.with_name('EXTRA')
            key = writer.derive_sig_key(game.read_bytes())
            previous_signature = writer.sign_save(key, payload)
            source_extra.write_bytes(previous_signature)
            def choose(button, path):
                with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')):
                    button.click()
                    wait()
            choose(panel.xbe_button, game)
            choose(panel.save_button, source)
            self.assertTrue(panel.owner_firing_check.isEnabled())
            self.assertFalse(panel.owner_firing_check.isChecked())
            self.assertNotIn('owner_firing', panel._collect_option_edits())
            panel.owner_firing_check.click()
            for check in panel._default_checks.values():
                check.setChecked(False)
            self.assertEqual(panel._collect_option_edits(), {'owner_firing': 0})
            dest = root / 'edited' / 'SAVEGAME.DAT'
            panel.out_field.setText(str(dest))
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Ok) as confirm, \
                    patch.object(QMessageBox, 'information') as done:
                panel.apply_button.click()
                wait()
            self.assertIn('Owner Firing set to Off', confirm.call_args.args[2])
            self.assertIn('Owner Firing set to Off', done.call_args.args[2])
            saved = dest.read_bytes()
            self.assertEqual(saved, payload[:at] + b'\0' + payload[at + 1:])
            self.assertTrue(writer.verify_extra(key, saved, dest.with_name('EXTRA').read_bytes()))
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(source_extra.read_bytes(), previous_signature)
            choose(panel.save_button, dest)
            self.assertFalse(panel.owner_firing_check.isEnabled())
            self.assertFalse(panel.owner_firing_check.isChecked())
            self.assertNotIn('owner_firing', panel._collect_option_edits())
            settings = root / 'Settings.DAT'
            settings.write_bytes(bytes(writer.SETTINGS_BLOCK_SIZE))
            choose(panel.save_button, settings)
            self.assertTrue(panel.owner_firing_check.isHidden())
            self.assertNotIn('owner_firing', panel._collect_option_edits())
