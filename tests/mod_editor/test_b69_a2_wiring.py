"""Behavioral checks for the protected J6/J9 bindings after the combined merge."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.apf_studio import catalog, models
from mod_editor.apf_studio.facade import ApfStudioFacade
from mod_editor.core import mod_build, nfl2k5_espn25_rosters as historic


class AppliedIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_build_summary_refresh_does_not_publish_a_build_choice(self):
        from PyQt5.QtWidgets import QWidget, QPlainTextEdit
        from mod_editor.gui.gameplay_project_ui import observe_build_choices
        panel = QWidget()
        summary = QPlainTextEdit(panel)
        summary.setReadOnly(True)
        notes = QPlainTextEdit(panel)
        changes = []
        observe_build_choices(panel, lambda: changes.append(notes.toPlainText()))
        summary.setPlainText('Project edit index 0: Equipment / shoes01')
        summary.setPlainText('Project edit index 0: Equipment / shoes01')
        self.assertEqual(changes, [])
        notes.setPlainText('Authored build notes')
        self.assertEqual(changes, ['Authored build notes'])
        panel.deleteLater()

    def test_historic_hold_refuses_before_reading_resources_or_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'copy.iso'
            # Beta 72.1 names a vanished source before any build work, so this
            # fixture's source has to exist for the historic hold to be reached.
            (Path(folder) / 'source.iso').write_bytes(b'')
            plan = mod_build.BuildPlan(source=str(Path(folder) / 'source.iso'),
                                       target=str(target), espn25_rosters=True)
            with patch.object(mod_build.tt, 'is_disc_image', return_value=True), \
                 patch.object(mod_build.tt, '_naming_source_preflight', return_value=None), \
                 patch.object(historic, 'read_resources') as read:
                with self.assertRaisesRegex(ValueError, 'Historic'):
                    mod_build.build(plan)
                read.assert_not_called()
            self.assertFalse(target.exists())

    def test_csv_registry_api_identifies_its_real_writer_module(self):
        import json
        from mod_editor.capabilities.validate_registry import _command_module
        root = Path(__file__).resolve().parents[2]
        registry = json.loads((root / 'mod_editor/capabilities/registry.v1.json').read_text())
        row = next(row for row in registry['capabilities'] if row['id'] == 'nfl2k5.rosters.player_csv')
        self.assertEqual(_command_module(row['backend']['command'], row['id']),
                         'mod_editor/core/nfl2k5_roster_records.py')

    def test_applied_scheme_cards_reach_the_real_facade_and_export_stays_export_only(self):
        cards = {card.capability_id: card for card in catalog.build_capability_cards()}
        # Beta 71 hides the duplicate scheme controls from the integrated book workflow (Book Identity points
        # at CPU Play Calling), so the offensive schemes card is a proof boundary while never_call stays editable.
        for feature, expected in (('offensive_schemes', models.ApfStatus.EVIDENCE), ('never_call', models.ApfStatus.EDITABLE)):
            key = 'apf2k8.playbooks.' + feature
            with self.subTest(capability=key):
                self.assertEqual(cards[key].status, expected)
                binding = models.CAPABILITY_ACTION_BINDINGS[key]
                self.assertEqual(binding.handler_id, 'playbooks.cpu_playcalling')
                self.assertTrue(callable(getattr(ApfStudioFacade, binding.replace_method)))
                self.assertTrue(callable(getattr(ApfStudioFacade, binding.revert_method)))
        key = 'apf2k8.playbooks.scheme_spreadsheet'
        self.assertEqual(cards[key].status, models.ApfStatus.EXPORT_ONLY)
        self.assertTrue(callable(ApfStudioFacade.playcalling_scheme_csv))


if __name__ == '__main__':
    unittest.main()
