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
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
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
        unions = [('m3', mode.REQUESTS), ('full', REQUESTS), ('budget', budget)]
        unions += [(owner, mode.REQUESTS + tuple(r for r in REQUESTS if r[0] == owner)) for owner in owners]
        # b778 ai8/xs1: the full union is a v4 image (ai8's third-down owner is the 192-byte spill) and the beta62
        # budget is already v4. M3's fixed 4 KiB state page shortens the v3 data run, so the late owners that sat in
        # its last page now fall whole into the pool. These are the only rows that leave a v3 address; every other
        # v3 row keeps its address, and the pool rows keep their owner, kind, size and alignment.
        spills = {
            'full': {('nfl2k5_cpu_third_down', 'code', 0)},
            'budget': {('nfl2k5_star_career', 'code', 0), ('nfl2k5_star_career', 'data', 0),
                       ('nfl2k5_cpu_money_downs_late', 'code', 0),
                       ('nfl2k5_cpu_money_downs_late_state', 'data', 0),
                       ('nfl2k5_cpu_third_down', 'code', 0)},
        }
        for label, requests in unions:
            with self.subTest(owners=sorted({r[0] for r in requests})):
                before = space.plan(old_requests(requests))
                after = space.plan(requests)
                # An owner may occupy multiple page tails. Preserve/check each
                # fragment instead of overwriting the first with the last.
                current = {(r['owner'], r['kind'], r.get('owner_offset', 0)): r
                           for r in after['allocations']}
                spilled = set()
                for row in before['allocations']:
                    key = (row['owner'], row['kind'], row.get('owner_offset', 0))
                    if (row['owner'], row['kind']) == (mode.OWNER, 'code'):
                        continue
                    new = current[key]
                    if new == row:
                        continue
                    if new['va'] >= space.POOL_VA:
                        # A v4 pool row: new storage, so its address may move when the pool grows. It must stay the
                        # same allocation, and only a late owner may spill out of v3.
                        self.assertIn(row['owner'], space.LATE_OWNERS, f"{key} left v3 but is not a late owner")
                        self.assertEqual((row['owner'], row['kind'], row['size'], row['align']),
                                         (new['owner'], new['kind'], new['size'], new['align']),
                                         f"{key} changed allocation")
                        spilled.add(key)
                        continue
                    if (row['kind'] == 'code' and row['owner'] in (runtime.OWNER, *space.LATE_OWNERS)
                            and (row['owner'], row['kind']) not in space.TAIL_OWNERS):
                        # Code placed after the promoted MyCareer code follows its size: beta 71's sprite scorebug
                        # runtime (outgrew its beta-61 slot), beta 76's K128 (k1) and the beta 77 late owners letter
                        # grades and their progression row (f4/f4b). Honors code (f5) is a gap owner that moves into the
                        # 8 KiB footprint M3 leaves behind. b77-i2 measured it: on every union exactly these five code
                        # rows move. Static tail owners (period goalposts code, honors data) and every data/RO row,
                        # late or not, must keep their addresses.
                        self.assertEqual((row['owner'], row['kind'], row['size'], row['align']),
                                         (new['owner'], new['kind'], new['size'], new['align']),
                                         f"{key} changed allocation")
                        continue
                    self.fail(f"{key} moved inside v3")
                self.assertEqual(spilled, spills.get(label, set()), f"{label}: unexpected v4 spill")
                self.assertEqual(current[mode.OWNER, 'code', 0]['size'], 20480)
                extra = current[mode.EXTRA_OWNER, 'data', 0]
                self.assertEqual((extra['va'], extra['size']), (mode.EXTRA_VA, 4096))
                # The six fixed v3 regions never change; v4 only appends the pool, and the fixed state page is why
                # the budget and full-union pools are 2 and 3 pages (b778 ai8/xs1).
                self.assertEqual(before['regions'][:6], after['regions'][:6])
                expected_size = {'full': space.SCALE3_FILE_SIZE + 2 * space.PAGE,
                                 'budget': space.SCALE3_FILE_SIZE + 3 * space.PAGE}.get(label, space.SCALE3_FILE_SIZE)
                self.assertEqual(after['file_size'], expected_size)
                if label == 'budget':
                    self.assertEqual(before['file_size'], space.SCALE3_FILE_SIZE + 2 * space.PAGE)
                elif label == 'full':
                    self.assertEqual(before['file_size'], space.SCALE3_FILE_SIZE)
                else:
                    self.assertEqual(before['file_size'], after['file_size'])
                if after['version'] == 4:
                    self.assertEqual((after['regions'][6]['kind'], after['regions'][6]['size']),
                                     ('pool', expected_size - space.SCALE3_FILE_SIZE))
                else:
                    self.assertEqual(len(after['regions']), 6)

    def test_separate_rw_request_is_fixed_and_capacity_is_not_borrowed(self):
        for request in ((mode.EXTRA_OWNER, 'data', 8192, 16),
                        (mode.EXTRA_OWNER, 'code', 4096, 16),
                        (mode.EXTRA_OWNER, 'data', 4096, 32)):
            with self.subTest(request=request), self.assertRaises(ValueError):
                space.plan((request,))
        # b778-xs1: a large RW owner never borrows M3's fixed page: it lands whole in the v4 pool instead
        report = space.plan(mode.REQUESTS + (('other_large_state', 'data', 80*1024, 16),))
        other = next(a for a in report['allocations'] if a['owner'] == 'other_large_state')
        m3 = next(a for a in report['allocations'] if a['owner'] == mode.EXTRA_OWNER)
        self.assertGreaterEqual(other['va'], space.POOL_VA)
        self.assertEqual((m3['va'], m3['size']), (mode.EXTRA_VA, 4096))

    def test_full_reservations_cannot_overlap_m3_runtime_state(self):
        rows = space.plan(REQUESTS)['allocations']
        state = next(r for r in rows if (r['owner'], r['kind']) == (mode.OWNER, 'data'))
        # A placement regression into even the last unused word of the primary
        # state must fail before any executable or owner digest can be written.
        with patch.object(space, 'MYCAREER_M3_STATE_VA', state['va'] + state['size'] - 4):
            with self.assertRaisesRegex(ValueError, 'reservation overlap'):
                space.plan(REQUESTS)


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
