"""Fixed allocator-owned slots preserve every installed feature in any order."""
from pathlib import Path
import hashlib
import itertools
import json
import os
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor import test_nfl2k5_allocator_scaleout as fixtures


class FixedSlots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.SyntheticTests.setUpClass()
        cls.addClassCleanup(fixtures.SyntheticTests.doClassCleanups)
        cls.retail = fixtures.SyntheticTests.retail
        cls.requests = tuple(r for r in space.dormant_union() if r[0] not in space.DIRECTORY_CODE_OWNERS)
        cls.base = space.apply(cls.retail, cls.requests)[0]

    def test_every_subset_and_insertion_order_preserves_existing_feature_bytes(self):
        final = []
        for order in itertools.permutations(space.DIRECTORY_CODE_REQUESTS):
            current = self.base
            for request in order:
                old = space.layout(current)['allocations']
                extended, receipt = space.extend_scaleout(current, (request,))
                new = space.layout(extended)['allocations']
                self.assertEqual(len(extended), len(current))
                self.assertEqual(receipt['directory_tail_reassigned_bytes'], request[2])
                for row in old:
                    if row['owner'] != space.DIRECTORY_OWNER:
                        self.assertIn(row, new)
                        at, size = row['raw'], row['size']
                        self.assertEqual(current[at:at+size], extended[at:at+size])
                # Same owner content in every permutation, independent of order.
                code = bytes([space.DIRECTORY_CODE_OWNERS.index(request[0])+1])*request[2]
                current = space.install_code(extended, request[0], code)[0]
                self.assertEqual(space.status(current), 'applied')
            final.append(current)
        self.assertTrue(all(blob == final[0] for blob in final))

    def test_every_subset_accounts_for_exactly_one_directory_page(self):
        for mask in range(8):
            active = tuple(r for i,r in enumerate(space.DIRECTORY_CODE_REQUESTS) if mask & (1<<i))
            report = space.plan(self.requests+active)
            rows = [r for r in report['allocations'] if r['owner'] == space.DIRECTORY_OWNER
                    or r['owner'] in space.DIRECTORY_CODE_OWNERS]
            coverage = bytearray(space.PAGE)
            for row in rows:
                at = row['raw']-space.SCALE_DIRECTORY
                self.assertFalse(any(coverage[at:at+row['size']]))
                coverage[at:at+row['size']] = b'\1'*row['size']
            self.assertEqual(coverage, b'\1'*space.PAGE)
            self.assertEqual(report['capacity']['code']['capacity_bytes'], 106496+sum(r[2] for r in active))
            image = space.apply(self.retail, self.requests+active)[0]
            self.assertEqual(space.status(image), 'applied')
            self.assertEqual(space.apply(image)[0], image)

    def test_inactive_slot_cannot_be_blessed_or_reassigned_when_nonzero(self):
        image = space.extend_scaleout(self.base, (space.DIRECTORY_CODE_REQUESTS[2],))[0]
        at = space.SCALE_DIRECTORY+space.PAGE-1  # inactive tap-burst slot
        bad = bytearray(image);bad[at] = 1
        self.assertEqual(space.status(bytes(bad)), 'foreign')
        with self.assertRaisesRegex(ValueError, 'inactive directory slot'):
            space._seal_scaleout(bad, self.requests+(space.DIRECTORY_CODE_REQUESTS[2],))
        with self.assertRaises(ValueError):
            space.extend_scaleout(bytes(bad), (space.DIRECTORY_CODE_REQUEST,))

    def test_every_named_slot_rejects_changed_contract_and_metadata_overflow(self):
        seals = dict(code_sha256='0'*64, read_only_sha256='1'*64)
        for request in space.DIRECTORY_CODE_REQUESTS:
            owner,kind,size,align = request
            for wrong in ((owner,'data',size,align),(owner,kind,size+16,align),(owner,kind,size,32)):
                with self.assertRaisesRegex(ValueError, 'directory code'):
                    space.plan([wrong])
            budget = space._directory_budget([request])
            with patch.object(space.zlib,'compress',return_value=b'x'*(budget-76)):
                self.assertEqual(len(space._scale_directory([request],seals)),4096)
            with patch.object(space.zlib,'compress',return_value=b'x'*(budget-75)):
                with self.assertRaisesRegex(ValueError, 'directory capacity'):
                    space._scale_directory([request],seals)


@unittest.skipUnless(all(os.environ.get(k) for k in ('B77_RO1_XBE','B77_RO1_PICKS','B77_RO1_HBACK')),
                     'private base XBE and authored ro1 plans required')
class NativeCoexistence(unittest.TestCase):
    def test_all_three_features_compose_in_both_orders_and_replay(self):
        from mod_editor.core import nfl2k5_draft_picks as dp, nfl2k5_hback as hb, nfl2k5_abilities_runtime as abilities
        base = Path(os.environ['B77_RO1_XBE']).read_bytes()
        picks = json.loads(Path(os.environ['B77_RO1_PICKS']).read_text())
        hback = json.loads(Path(os.environ['B77_RO1_HBACK']).read_text())
        one = hb.apply(dp.apply(abilities.apply(base)[0], picks)[0],hback)[0]
        two = abilities.apply(hb.apply(dp.apply(base,picks)[0],hback)[0])[0]
        self.assertEqual(one,two)
        self.assertEqual(abilities.apply(one)[0],one)
        self.assertEqual(dp.apply(one,picks)[0],one)
        self.assertEqual(hb.apply(one,hback)[0],one)
        self.assertEqual(len(one),len(base))
        for row in space.layout(base)['allocations']:
            if row['owner'] != space.DIRECTORY_OWNER:
                self.assertIn(row,space.layout(one)['allocations'])
        with patch.object(dp,'REQUESTS',((dp.LEGACY_OWNER,'code',dp.CODE_SIZE,16),)), \
             patch.object(hb,'REQUESTS',((hb.LEGACY_OWNER,'code',hb.SIZE,16),)):
            legacy = hb.apply(dp.apply(base,picks)[0],hback)[0]
        self.assertEqual(dp.apply(legacy,picks)[0],legacy)
        self.assertEqual(hb.apply(legacy,hback)[0],legacy)
        self.assertEqual(hashlib.sha256(legacy).hexdigest(),
                         'ef8be562489291280681f4c4cd236ac5a52a175b95978af3f863d56159369294')


if __name__ == '__main__':
    unittest.main()
