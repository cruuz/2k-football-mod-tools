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
    def test_historic_hold_refuses_before_reading_resources_or_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'copy.iso'
            plan = mod_build.BuildPlan(source=str(Path(folder) / 'source.iso'),
                                       target=str(target), espn25_rosters=True)
            with patch.object(mod_build.tt, 'is_disc_image', return_value=True), \
                 patch.object(mod_build.tt, '_naming_source_preflight', return_value=None), \
                 patch.object(historic, 'read_resources') as read:
                with self.assertRaisesRegex(ValueError, 'Historic'):
                    mod_build.build(plan)
                read.assert_not_called()
            self.assertFalse(target.exists())

    def test_applied_scheme_cards_reach_the_real_facade_and_export_stays_export_only(self):
        cards = {card.capability_id: card for card in catalog.build_capability_cards()}
        for feature in ('offensive_schemes', 'never_call'):
            key = 'apf2k8.playbooks.' + feature
            with self.subTest(capability=key):
                self.assertEqual(cards[key].status, models.ApfStatus.EDITABLE)
                binding = models.CAPABILITY_ACTION_BINDINGS[key]
                self.assertEqual(binding.handler_id, 'playbooks.cpu_playcalling')
                self.assertTrue(callable(getattr(ApfStudioFacade, binding.replace_method)))
                self.assertTrue(callable(getattr(ApfStudioFacade, binding.revert_method)))
        key = 'apf2k8.playbooks.scheme_spreadsheet'
        self.assertEqual(cards[key].status, models.ApfStatus.EXPORT_ONLY)
        self.assertTrue(callable(ApfStudioFacade.playcalling_scheme_csv))


if __name__ == '__main__':
    unittest.main()
