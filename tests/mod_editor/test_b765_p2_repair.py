"""P2 native composition preserves p1 bytes and adds complete owner guards."""
from pathlib import Path
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765 import p1_repair, p2_repair
from mod_editor.core import nfl2k5_rdata_sites as sites
from mod_editor.core.nfl2k5_cave_oracle import XbeImage


class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get('B765_P2_V04_XBE')
        if not source:
            raise unittest.SkipTest('private v0.4 extraction not configured')
        cls.before = Path(source).read_bytes()
        if p1_repair.digest(cls.before) != p1_repair.V04_SHA256:
            raise unittest.SkipTest('private v0.4 extraction hash differs')

    def test_composes_with_p1_and_is_idempotent(self):
        fixed, receipt = p2_repair.repair(self.before)
        self.assertEqual(fixed, p1_repair.repair(self.before)[0])
        self.assertEqual(receipt['after_sha256'], p1_repair.FIXED_SHA256)
        self.assertTrue(receipt['outside_scope_identical'])
        self.assertTrue(receipt['studio_owner_validated'])
        self.assertFalse(receipt['modern_practice_squad'])
        replay, replay_receipt = p2_repair.repair(fixed)
        self.assertEqual(replay, fixed)
        self.assertEqual(replay_receipt['changed_bytes'], 0)

    def test_recorded_hash_cannot_authorize_foreign_screen_prerequisite(self):
        image = XbeImage(self.before)
        original = image.read(0x555098, 4)
        damaged, _ = sites.apply(self.before, [(
            'foreign_descriptor_fixture', 0x555098, original,
            bytes([original[0] ^ 1]) + original[1:])], 'test')
        recorded = p1_repair.digest(damaged)
        # Functional cut/menu spans and section digests still match p1's scope.
        p1_repair.repair(damaged, expected_input_sha256=recorded)
        with self.assertRaisesRegex(ValueError, 'foreign/mixed Practice Squad screen'):
            p2_repair.repair(damaged, expected_input_sha256=recorded)

    def test_unrecorded_input_hash_refuses(self):
        with self.assertRaisesRegex(ValueError, 'input SHA-256'):
            p2_repair.repair(self.before, expected_input_sha256='0' * 64)


if __name__ == '__main__':
    unittest.main()
