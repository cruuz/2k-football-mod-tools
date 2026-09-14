"""Exercise proposed protected integration without mutating the registry."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.capabilities import validate_registry
from mod_editor.core.capabilities import CapabilityRegistryLoader
from mod_editor.apf_studio import catalog, models, playcalling_service
from mod_editor.apf_studio.facade import ApfStudioFacade

ROOT = Path(__file__).resolve().parents[2]


class WiringTests(unittest.TestCase):
    def test_proposed_rows_and_bindings_render_with_real_facade_closure(self):
        data = json.loads(validate_registry.DEFAULT_REGISTRY.read_text())
        rows = json.loads((ROOT / 'docs/research/apf_b69_registry_rows.json').read_text())
        self.assertEqual(len(rows), 3)
        proposed_ids = {r['id'] for r in rows}
        self.assertEqual(len(proposed_ids), 3)
        data['capabilities'] = sorted([r for r in data['capabilities']
            if r['id'] not in proposed_ids] + rows, key=lambda r: r['id'])
        # The baseline has legacy evidence paths which are absent in this
        # worktree. Validate the whole schema and every NEW referenced file.
        validate_registry.validate_data(data, check_files=False)
        for row in rows:
            for filename in [row['backend']['module'], *row['evidence']]:
                self.assertTrue((ROOT / filename).is_file(), filename)
        bindings = dict(models.CAPABILITY_ACTION_BINDINGS)
        for feature in ('offensive_schemes', 'never_call'):
            key = 'apf2k8.playbooks.' + feature
            bindings[key] = replace(bindings['apf2k8.playbooks.cpu_playcalling'], capability_id=key)
            self.assertTrue(callable(getattr(ApfStudioFacade, bindings[key].replace_method)))
            self.assertTrue(callable(getattr(ApfStudioFacade, bindings[key].revert_method)))
        key = 'apf2k8.playbooks.scheme_spreadsheet'
        bindings[key] = models.CapabilityActionBinding(key, 'playbooks.cpu_playcalling',
            frozenset((models.ApfProductAction.PREVIEW, models.ApfProductAction.EXPORT)))
        self.assertTrue(callable(ApfStudioFacade.playcalling_scheme_csv))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'registry.json'
            path.write_bytes((json.dumps(data, indent=2, sort_keys=True) + '\n').encode())
            loader = CapabilityRegistryLoader(path)
            with patch.object(catalog, 'CapabilityRegistryLoader', return_value=loader), patch.object(models, 'CAPABILITY_ACTION_BINDINGS', bindings):
                cards = {c.capability_id: c for c in catalog.build_capability_cards()}
        for feature in ('offensive_schemes', 'never_call'):
            self.assertEqual(cards['apf2k8.playbooks.' + feature].status, models.ApfStatus.EDITABLE)
        self.assertEqual(cards[key].status, models.ApfStatus.EXPORT_ONLY)

    def test_csv_command_loads_reviewed_project_and_exports_without_build(self):
        facade = Mock()
        payload = b'\xef\xbb\xbfTeam,Bucket\nAuthored,Openers\n'
        facade.playcalling_scheme_csv.return_value = payload
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'calls.csv'
            with patch('mod_editor.apf_studio.facade.ApfStudioFacade', return_value=facade):
                self.assertEqual(playcalling_service.main(['--game-folder', folder,
                    '--project', 'authored.apf2k8mod', '--spreadsheet-team', '2',
                    '--output', str(output)]), 0)
            self.assertEqual(output.read_bytes(), payload)
        facade.load_source.assert_called_once()
        facade.load_project.assert_called_once_with(Path('authored.apf2k8mod'))
        facade.playcalling_scheme_csv.assert_called_once_with(2)
        facade.build.assert_not_called()
        facade.close.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
