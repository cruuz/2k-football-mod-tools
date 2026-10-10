"""PROVED OFFLINE: CPU fill ownership, exact reverts and native composition."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hashlib
import unittest

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core import nfl2k5_roster_fill_composition as chain
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, HAVE_UC


class CompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.economy = economy.apply(cls.retail)[0]
        cls.squad = squad.apply(cls.retail)[0]
        cls.combined = squad.apply(cls.economy)[0]

    def test_install_orders_are_identical_and_all_forms_are_idempotent(self):
        self.assertEqual(economy.apply(self.squad)[0], self.combined)
        for payload, expected in ((self.retail, ('retail', 'retail')),
                                  (self.economy, ('applied', 'retail')),
                                  (self.squad, ('retail', 'applied')),
                                  (self.combined, ('applied', 'applied'))):
            self.assertEqual((economy.status(payload), squad.status(payload)), expected)
            for module, state in zip((economy, squad), expected):
                if state == 'applied':
                    result, receipt = module.apply(payload)
                    self.assertEqual(result, payload)
                    self.assertEqual(receipt['changed_bytes'], 0)
        for section in _sections(self.combined):
            self.assertEqual(self.combined[section.header_offset + 36:section.header_offset + 56],
                             section_digest(self.combined, section))

    def test_both_revert_orders_restore_the_other_owner_then_exact_retail(self):
        for module, other, expected in ((economy, squad, self.squad),
                                        (squad, economy, self.economy)):
            alone = module.revert(self.combined, self.retail)[0]
            self.assertEqual(alone, expected)
            self.assertEqual(module.revert(alone, self.retail)[0], alone)
            self.assertEqual(other.revert(alone, self.retail)[0], self.retail)
            self.assertEqual(module.revert(module.apply(self.retail)[0], self.retail)[0], self.retail)
            self.assertEqual(module.apply(alone)[0], self.combined)

    def test_foreign_shared_bytes_and_partial_dependencies_are_never_normalized(self):
        addresses = (chain.ENTRY, chain.CONTINUATION, squad.SYMBOLS['ps_room'],
                     economy.SYMBOLS['economy_fill_gate'], 0x4FE7A0, 0xC3EE0)
        image = chain.XbeImage(self.combined)
        for address in addresses:
            damaged = chain.replace(self.combined, [(address, bytes([image.read(address, 1)[0] ^ 1]))],
                                    repin=True)[0]
            for module in (economy, squad):
                with self.subTest(address=hex(address), owner=module.__name__):
                    self.assertEqual(module.status(damaged), 'foreign')
                    with self.assertRaises(ValueError): module.apply(damaged)
                    with self.assertRaises(ValueError): module.revert(damaged, self.retail)
        for payload, edits in ((self.squad, [(chain.CONTINUATION, chain.CHAIN)]),
                               (self.economy, [(chain.ENTRY, chain.SQUAD_ENTRY)]),
                               (self.combined, [(chain.ENTRY, chain.ECONOMY_ENTRY)]),
                               (self.retail, [(chain.CONTINUATION, chain.CHAIN)])):
            damaged = chain.replace(payload, edits, repin=True)[0]
            self.assertEqual(economy.status(damaged), 'foreign')
            self.assertEqual(squad.status(damaged), 'foreign')

    def test_revert_requires_pinned_retail_and_preserves_unowned_edits(self):
        payload = chain.replace(self.combined, [(0x322DE0, b'\x04')], repin=True)[0]
        # DESIGN: an unrelated byte outside the owned spans must survive.
        for module in (economy, squad):
            payload = module.revert(payload, self.retail)[0]
            with self.assertRaisesRegex(ValueError, 'hash-pinned retail'):
                module.revert(self.combined, self.economy)
        expected = chain.replace(self.retail, [(0x322DE0, b'\x04')], repin=True)[0]
        self.assertEqual(payload, expected)

    def test_build_pipeline_installs_both_and_preserves_historic_release(self):
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        from mod_editor.core import nfl2k5_espn25_rosters as historic
        result, _ = tuning._apply_all(self.retail, None, catch_slider=False,
                                     franchise_economy=True, practice_squad=True)
        self.assertEqual(economy.status(result), 'applied')
        self.assertEqual(squad.status(result), 'applied')
        self.assertEqual(historic.xbe_status(result), 'applied')

    def test_rookie_table_preserves_contract_actions_and_editor_composition(self):
        from mod_editor.core import nfl2k5_franchise_edit_player as editor
        from mod_editor.core.nfl2k5_franchise_economy_code import ROOKIE_TABLE_VA, ROOKIE_TABLE
        self.assertEqual(ROOKIE_TABLE_VA, editor.ROWS_VA + editor.RETAIL_ROW_COUNT * editor.ROW_SIZE)
        self.assertEqual(ROOKIE_TABLE_VA + len(ROOKIE_TABLE), 0x521678)
        self.assertEqual(chain.XbeImage(self.combined).read(editor.ROWS_VA, 600),
                         chain.XbeImage(self.retail).read(editor.ROWS_VA, 600))
        combined = editor.apply(self.combined)[0]
        reverse = squad.apply(economy.apply(editor.apply(self.retail)[0])[0])[0]
        self.assertEqual(combined, reverse)
        for owner in (editor, economy, squad):
            self.assertEqual(owner.status(combined), 'applied')
            self.assertEqual(owner.apply(combined)[0], combined)
        self.assertEqual(editor.status(economy.revert(combined, self.retail)[0]), 'applied')

    def test_mycareer_cap_context_accepts_only_a_complete_economy(self):
        from mod_editor.core import nfl2k5_my_career_mode as career
        both = career.apply(self.combined)[0]
        self.assertEqual(both, squad.apply(economy.apply(career.apply(self.retail)[0])[0])[0])
        self.assertEqual(career.status(both), 'applied')
        self.assertEqual(career.apply(both)[0], both)
        self.assertEqual(economy.status(both), 'applied')
        cap = next(s for s in economy.sites() if s.va == 0x13EF17)
        orphan = chain.replace(self.retail, [(cap.va, cap.patched)], repin=True)[0]
        damaged = chain.replace(both, [(economy.SYMBOLS['economy_fill_gate'], b'\xcc')], repin=True)[0]
        for payload in (orphan, damaged):
            self.assertEqual(career.status(payload), 'foreign')
            with self.assertRaises(ValueError): career.apply(payload)

    def test_arena_projection_keeps_the_combined_owner_and_revert_dependency(self):
        from mod_editor.core import nfl2k5_roster_arena_growth as growth
        grown = growth.apply(self.combined)[0]
        other_order = economy.apply(growth.apply(self.squad)[0])[0]
        self.assertEqual(grown, other_order)
        self.assertEqual(growth.status(grown), 'applied')
        self.assertEqual(economy.status(grown), 'applied')
        self.assertEqual(squad.status(grown), 'applied')
        reverted = economy.revert(grown, self.retail)[0]
        self.assertEqual(growth.status(reverted), 'applied')
        self.assertEqual(squad.status(reverted), 'applied')
        self.assertEqual(economy.status(reverted), 'retail')
        with self.assertRaisesRegex(ValueError, 'revert arena growth'):
            squad.revert(grown, self.retail)

    def test_manifest_reserves_the_full_economy_and_shared_chain(self):
        from pathlib import Path
        from mod_editor.core.nfl2k5_cave_oracle import ReservationManifest, DEFAULT_MANIFEST
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, chain.XbeImage(self.retail),
                                            source_root=Path(__file__).resolve().parents[2])
        for site in economy.sites():
            spans = [s for s in manifest.spans if s.detail.startswith('nfl2k5_franchise_economy:')]
            for address in range(site.va, site.va + len(site.patched)):
                self.assertTrue(any(s.start <= address < s.end for s in spans), hex(address))
        for address, size in ((chain.ENTRY, 6), (chain.CONTINUATION, len(chain.CHAIN))):
            self.assertTrue(any(s.start == address and s.end == address + size
                                and s.detail.startswith('nfl2k5_roster_fill_composition:')
                                for s in manifest.spans))

    @unittest.skipUnless(HAVE_UC, 'Unicorn is not installed')
    def test_native_fill_capacity_cap_minimums_and_transaction_ownership(self):
        from tools.franchise_economy.composition_probe import run, CASES
        result = run(self.combined)
        self.assertEqual(len(result['cases']), len(CASES))
        self.assertEqual(result['xbe_sha256'], hashlib.sha256(self.combined).hexdigest())
        self.assertFalse(result['runtime_witnessed'])


if __name__ == '__main__':
    unittest.main()
