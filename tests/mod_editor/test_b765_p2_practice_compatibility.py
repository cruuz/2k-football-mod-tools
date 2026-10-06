"""Exercise the real Studio dispatcher on legacy and retired reserve owners."""
from pathlib import Path
import hashlib
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_throw_tuning as tuning
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_squad_screen as screen
from mod_editor.core import nfl2k5_franchise_practice as practice
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_rdata_sites as sites
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_practice_squad_screen_fixture import XBE, composed
from tools.b765 import p1_repair


def build(payload, **options):
    return tuning._apply_all(payload, None, catch_slider=False, **options)


def legacy_cuts(payload):
    cut = next(s for s in ps.sites() if s.va == 0x2BFA6E)
    return sites.apply(payload, [("legacy_cut_fixture", cut.va, cut.retail, cut.patched)], "test")[0]


@unittest.skipUnless(XBE.is_file(), "private pinned USA XBE absent")
class DispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise unittest.SkipTest("private USA XBE hash differs")
        cls.base = composed(cls.retail)
        cls.fixed = screen.apply(cls.base)[0]
        code, data = screen.allocations(cls.fixed)
        _, cls.labels = screen.code_for(cls.fixed, code['va'], data['va'])
        cls.legacy = legacy_cuts(sites.apply(cls.fixed, [(
            "legacy_screen_fixture", practice.COACH_DESK_ROWS_PTR_VA,
            struct.pack('<I', practice.NEW_ROW_VA), struct.pack('<I', cls.labels['menu']))], "test")[0])

    def test_old_storage_is_upgraded_without_screen_option(self):
        baseline, _ = build(self.retail, practice_squad=True)
        result, receipt = build(legacy_cuts(baseline), practice_squad=True)
        self.assertEqual(result, baseline)
        self.assertGreater(receipt['practice_squad_patch']['changed_bytes'], 0)
        self.assertNotIn('practice_squad_screen_patch', receipt)
        again, replay = build(result, practice_squad=True)
        self.assertEqual(again, result)
        self.assertEqual(replay['practice_squad_patch']['changed_bytes'], 0)

    def test_installed_screen_retires_even_when_screen_option_is_off(self):
        # Historic-release normalization is an independent existing build step.
        expected, _ = build(self.fixed, practice_squad=True)
        result, receipt = build(self.legacy, practice_squad=True)
        self.assertEqual(result, expected)
        self.assertTrue(receipt['practice_squad_screen_patch']['screen_removed'])
        self.assertGreater(receipt['practice_squad_patch']['changed_bytes'], 0)
        self.assertEqual(space.layout(result)['allocations'], space.layout(self.legacy)['allocations'])
        code, _ = screen.allocations(result)
        self.assertEqual(XbeImage(result).read(code['va'], code['size']),
                         XbeImage(self.legacy).read(code['va'], code['size']))
        self.assertEqual(build(result, practice_squad=True)[0], result)

    def test_prepared_owner_stays_empty_when_screen_option_is_off(self):
        prepared, _ = space.apply(self.base, screen.REQUESTS, scaleout=True)
        result, receipt = build(prepared, practice_squad=True)
        self.assertNotIn('practice_squad_screen_patch', receipt)
        code, _ = screen.allocations(result)
        self.assertEqual(XbeImage(result).read(code['va'], code['size']), b'\xcc' * code['size'])

    def test_without_reserve_compatibility_no_screen_repair_is_selected(self):
        result, receipt = build(self.legacy)
        self.assertEqual(result, self.legacy)
        self.assertNotIn('practice_squad_patch', receipt)
        self.assertNotIn('practice_squad_screen_patch', receipt)

    def test_installed_foreign_menu_refuses_without_changing_input(self):
        broken, _ = sites.apply(self.legacy, [(
            "foreign_menu_fixture", practice.COACH_DESK_ROWS_PTR_VA,
            struct.pack('<I', self.labels['menu']), b'\x00' * 4)], "test")
        snapshot = bytes(broken)
        with self.assertRaisesRegex(ValueError, 'installed Practice Squad screen is foreign'):
            build(broken, practice_squad=True)
        self.assertEqual(broken, snapshot)


class DiscDispatcherTests(unittest.TestCase):
    def test_actual_v04_deferred_stage_matches_native_repair(self):
        source = os.environ.get('B765_P2_V04_XBE')
        if not source:
            self.skipTest('private v0.4 extraction not configured')
        before = Path(source).read_bytes()
        self.assertEqual(p1_repair.digest(before), p1_repair.V04_SHA256)
        # This is the real deferred build stage. Installed unrelated option
        # reconciliation belongs to the containing build, and is not claimed here.
        result, receipt = build(before, practice_squad=True, _defer_runtime_settings=True)
        self.assertEqual(result, p1_repair.repair(before)[0])
        self.assertEqual(p1_repair.digest(result), p1_repair.FIXED_SHA256)
        self.assertTrue(receipt['practice_squad_screen_patch']['screen_removed'])
        self.assertEqual(build(result, practice_squad=True, _defer_runtime_settings=True)[0], result)


if __name__ == '__main__':
    unittest.main()
