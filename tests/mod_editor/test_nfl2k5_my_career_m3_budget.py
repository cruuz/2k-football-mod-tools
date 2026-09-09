"""M3 reservation promotion, every old owner address, and rebuild refusals."""
from pathlib import Path
import hashlib
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_my_career as legacy
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
from tests.nfl2k5_allocator_stack import REQUESTS
from tests.nfl2k5_my_career_fixture import XBE


def old_requests(requests):
    return tuple((o, k, 8192 if (o, k) == (mode.OWNER, 'code') else n, a)
                 for o, k, n, a in requests if o != mode.EXTRA_OWNER)


class PlanningTests(unittest.TestCase):
    def test_full_budget_gate_and_each_pair_preserve_every_other_address(self):
        budget = json.loads((ROOT / 'tests/fixtures/nfl2k5_allocator_beta62_requests.json').read_text())
        own = [tuple(r) for r in budget if r[0] in (mode.OWNER, mode.EXTRA_OWNER)]
        self.assertEqual(own, list(mode.REQUESTS))
        owners = sorted({r[0] for r in REQUESTS} - {mode.OWNER, mode.EXTRA_OWNER})
        unions = [mode.REQUESTS, REQUESTS, budget]
        unions += [mode.REQUESTS + tuple(r for r in REQUESTS if r[0] == owner) for owner in owners]
        for requests in unions:
            with self.subTest(owners=sorted({r[0] for r in requests})):
                before = space.plan(old_requests(requests))
                after = space.plan(requests)
                current = {(r['owner'], r['kind']): r for r in after['allocations']}
                for row in before['allocations']:
                    if (row['owner'], row['kind']) != (mode.OWNER, 'code'):
                        self.assertEqual(current[row['owner'], row['kind']], row)
                self.assertEqual(current[mode.OWNER, 'code']['size'], 16384)
                extra = current[mode.EXTRA_OWNER, 'data']
                self.assertEqual((extra['va'], extra['size']), (mode.EXTRA_VA, 4096))
                self.assertEqual(before['file_size'], after['file_size'])
                self.assertEqual(before['regions'], after['regions'])

    def test_separate_rw_request_is_fixed_and_capacity_is_not_borrowed(self):
        for request in ((mode.EXTRA_OWNER, 'data', 8192, 16),
                        (mode.EXTRA_OWNER, 'code', 4096, 16),
                        (mode.EXTRA_OWNER, 'data', 4096, 32)):
            with self.subTest(request=request), self.assertRaises(ValueError):
                space.plan((request,))
        with self.assertRaises(ValueError):
            space.plan(mode.REQUESTS + (('other_large_state', 'data', 80*1024, 16),))


@unittest.skipUnless(XBE.is_file(), 'private USA retail XBE required')
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16*1024**2:
            raise unittest.SkipTest('retail XBE exceeds 16 MiB')
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE evidence pin differs')

    def test_old_reserved_executable_refuses_before_any_install(self):
        old = space.apply(self.retail, old_requests(REQUESTS), scaleout=True)[0]
        self.assertEqual(space.status(old), 'applied')
        self.assertEqual(mode.status(old), 'foreign')
        with patch.object(space, 'install_code', side_effect=AssertionError('mutation before refusal')):
            with self.assertRaises(ValueError):
                mode.apply(old)
        with self.assertRaisesRegex(ValueError, 'rebuild from base'):
            space.apply(old, REQUESTS, scaleout=True)

    def test_code_and_both_state_blocks_are_sealed_and_replay_exactly(self):
        payload = mode.apply(space.apply(self.retail, REQUESTS, scaleout=True)[0])[0]
        self.assertEqual(mode.status(payload), 'applied')
        replay, receipt = mode.apply(payload)
        self.assertEqual(replay, payload)
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertEqual(receipt['data_capacity'], 8192)
        code, data = legacy.allocations(payload)
        im = XbeImage(payload)
        self.assertFalse(im.section(code['va']).writable)
        for va in (data['va'], mode.EXTRA_VA):
            self.assertTrue(im.runtime_writable(va, 4096))
            self.assertEqual(im.read(va, 4096), bytes(4096))
            damaged = bytearray(payload)
            damaged[im.offset(va)] = 1
            self.assertEqual(mode.status(bytes(damaged)), 'foreign')

    def test_native_cut_and_partial_squad_companions_refuse_before_install(self):
        from mod_editor.core import nfl2k5_practice_squad as ps
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        damaged=[repin_edit(self.retail,0x2BF9A0,b'\xcc')]
        damaged += [repin_edit(self.retail,s.va,s.patched) for s in ps.sites()
                    if s.name in ('ps_cut','ps_append')]
        for payload in damaged:
            self.assertEqual(mode.status(payload),'foreign')
            with patch.object(space,'install_code',side_effect=AssertionError('mutation before refusal')):
                with self.assertRaises(ValueError):
                    mode.apply(payload)


if __name__ == '__main__':
    unittest.main()
