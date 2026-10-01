"""PROVED OFFLINE only: execute pinned retail selectors with the v3 detours.

No Xenia, game launch, disc build or image export. Uses the beta-67 PPC ABI
adapters and explicit RNG/kicker boundary inputs. See the A3 lab note.
"""
from collections import Counter
import gc
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.core import apf2k8_playcall_model as model
from tests.mod_editor import test_apf_playcall_research_native as fixture
from tests.mod_editor import test_apf_b72_personnel_rows_native as personnel_fixture
from tests.mod_editor.test_apf_b76_situation_weights import rows
from tools.apf_playcall_research_probe import BOOK, MASTER, MANAGER, OUTPUT, TEAM, GAME


def install(machine, patch):
    image = bytearray(machine.image)
    for address, value in patch.words:
        payload = struct.pack('>I', value)
        machine.cpu.mem_write(address, payload)
        image[address-mask.IMAGE_BASE:address-mask.IMAGE_BASE+4] = payload
    machine.image = bytes(image)


class WeightNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.NativePlaycallTests.setUpClass.__func__(cls)
        if cls.tu is None: raise AssertionError('A3 requires both owned profiles')
        cls.evidence = {'classification': 'PROVED OFFLINE', 'runtime_status': 'UNWITNESSED',
                        'master_instructions': cls.initializer_steps, 'cases': []}

    @classmethod
    def tearDownClass(cls):
        target = os.environ.get('APF_A3_RECEIPT')
        if target:
            Path(target).write_text(json.dumps(cls.evidence, indent=2)+'\n')

    machine = fixture.NativePlaycallTests.machine

    def vector(self, machine, category=False, row=10):
        return personnel_fixture.PersonnelNativeTests.vector(self, machine, category, row)

    def test_every_scrimmage_key_and_factor_matches_native_buffers(self):
        checks = []
        for updated in (False, True):
            image = self.tu if updated else self.base
            for down in range(1, 5):
                for yards in (1, 5, 8):
                    situation = model.Situation(down, yards, 50, 1, 900, 0, 3)
                    key = mask.situation_key(situation)
                    factors = {'2': .25, '14': .5, '24': 4.}
                    patch = mask.compile_patch(image, {}, rows(key, {'6': 10}), rows(key, factors))
                    m = self.machine(130, updated, down=down, yards=yards, goal_yards=50, run_share=0)
                    m.normalize()
                    install(m, patch)
                    vector = self.vector(m)
                    original = model.formation_weights(self.books[130].body, self.master, 6, situation, run_share=0)
                    self.assertEqual(vector, tuple((f, model.f32(w*factors.get(str(f), 1))) for f, w in original))
                    requested = model.requested_offense_row(situation)
                    expected = model.category_weights(self.books[130].body, self.master, requested, situation,
                                                      run_share=0, personnel_rows={'6': 10})
                    self.assertEqual(self.vector(m, True, requested), expected)
                    checks.append({'profile': patch.profile.name, 'key': key, 'formation_vector': vector})
                    del m
                    gc.collect()
        self.evidence['all_scrimmage_keys'] = checks

    def test_vectors_distribution_isolation_and_full_cpu_calls(self):
        for updated in (False, True):
            image = self.tu if updated else self.base
            patch = mask.compile_patch(image, {}, {}, rows())
            for down, yards in ((3, 8), (1, 10), (3, 5)):
                original = self.machine(130, updated, down=down, yards=yards, goal_yards=50, run_share=0)
                changed = self.machine(130, updated, down=down, yards=yards, goal_yards=50, run_share=0)
                install(changed, patch)
                before, after = self.vector(original), self.vector(changed)
                expected = tuple((f, w*(4 if f == 14 and down == 3 and yards == 8 else 1)) for f, w in before)
                self.assertEqual(after, expected)
                # No change to the preceding category lottery.
                self.assertEqual(self.vector(original, True), self.vector(changed, True))
                for m in (original, changed): m.observers.clear()
                distributions = []
                for m in (original, changed):
                    counts = Counter()
                    for i in range(96):
                        m.random_boundaries((i+.5)/96, 1, 0xFD0 if updated else 0)
                        pointer = m.call(m.va(0x848693F8), MANAGER, 14, MASTER+0x44+6*16, 0, 0, bound=2000000)
                        counts[(pointer-MASTER-0x244)//184] += 1
                    distributions.append(dict(counts))
                if (down, yards) == (3, 8):
                    self.assertEqual(distributions, [{2: 32, 14: 32, 24: 32}, {2: 16, 14: 64, 24: 16}])
                else: self.assertEqual(*distributions)
                full = [[], []]
                for i in range(24):
                    for j, m in enumerate((original, changed)):
                        m.configure(down=down, yards=yards, goal_yards=50, run_share=0, fraction=(i+.5)/24)
                        m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
                        full[j].append(bytes(m.cpu.mem_read(OUTPUT, 20)).hex())
                if (down, yards) != (3, 8): self.assertEqual(*full)
                else: self.assertNotEqual(*full)
                self.assertEqual([v[:8] for v in full[0]], [v[:8] for v in full[1]])
                cpu_counts = [dict(Counter((int(v[8:16], 16)-MASTER-0x244)//184 for v in arm)) for arm in full]
                self.evidence['cases'].append({'profile': patch.profile.name, 'down': down, 'yards': yards,
                    'native_weights_before': before, 'native_weights_after': after,
                    'formation_selector_draws': 96, 'counts_before': distributions[0], 'counts_after': distributions[1],
                    'full_cpu_calls': 24, 'full_cpu_equal': full[0] == full[1], 'full_cpu_formation_counts': cpu_counts,
                    'instructions': [original.steps, changed.steps]})
                del original, changed, m
                gc.collect()

    def test_try_key_exclusions_rows_and_scrimmage_independence(self):
        for updated in (False, True):
            image = self.tu if updated else self.base
            excluded = {'O-ManBlock': [[] for _ in range(13)]}; excluded['O-ManBlock'][12] = [2]
            patch = mask.compile_patch(image, excluded, rows(12, {'6': 10}), rows(12))
            for phase in (3, 4):
                m = self.machine(130, updated, down=4, yards=2, goal_yards=2, run_share=0)
                install(m, patch)
                m.put(GAME+(0x30 if updated else 0)+0x34, phase)
                vector = self.vector(m)
                situation = model.Situation(4, 2, 2, 1, 900, 0, 3)
                retail = model.formation_weights(self.books[130].body, self.master, 6, situation, run_share=0)
                expected_forms = tuple((f, w*(4 if f == 14 and phase == 3 else 1)) for f, w in retail if phase != 3 or f != 2)
                self.assertEqual(vector, expected_forms)
                categories = self.vector(m, True)
                situation = model.Situation(4, 2, 2, 1, 900, 0, 3)
                expected = model.category_weights(self.books[130].body, self.master, 10, situation,
                    run_share=0, personnel_rows={'6': 10} if phase == 3 else {})
                if phase == 3: expected, _ = mask.filter_categories(self.books[130].body, self.master, expected, [2])
                self.assertEqual(categories, expected)
                self.evidence['cases'].append({'profile': patch.profile.name, 'phase': phase,
                    'try_vector': vector, 'category_vector': categories})
            # Execute the actual try decision through tuple commit. Native
            # score -5 in the fourth period requests ordinary two-point offense.
            m = self.machine(130, updated, down=4, yards=2, goal_yards=2, period=4, score=-5, clock=110, run_share=0)
            install(m, patch)
            m.put(GAME+(0x30 if updated else 0)+0x34, 3)
            m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
            category = (m.get(OUTPUT)-MASTER-0x44)//16
            formation = (m.get(OUTPUT+4)-MASTER-0x244)//184
            self.assertTrue(0 <= category < 28 and 0 <= formation < 151)
            self.assertEqual(m.get(mask.RECEIPT_START+24), 12)
            self.evidence['cases'].append({'profile': patch.profile.name, 'full_try_category': category,
                'full_try_formation': formation, 'key': 12, 'instructions': m.steps})

    def test_no_policy_bad_headers_and_empty_draw_retain_retail(self):
        for updated in (False, True):
            image = self.tu if updated else self.base
            all_forms = [r.formation_index for r in self.books[130].records if r.populated and r.formation_index < 151]
            masks = {'O-ManBlock': [[] for _ in range(13)]}; masks['O-ManBlock'][8] = all_forms
            for policies, weights, corrupt in (({}, {}, None), ({}, {'OtherBook': rows()['O-ManBlock']}, None),
                    ({}, rows(), (mask.DATA_START+4, 99)), ({}, rows(), (mask.DATA_START+8, 48)),
                    ({}, rows(), (mask.DATA_START+16+288+4, 0xFFFFFFFF)), (masks, rows(), None)):
                baseline = self.machine(130, updated, down=3, yards=8, goal_yards=50, run_share=0)
                changed = self.machine(130, updated, down=3, yards=8, goal_yards=50, run_share=0)
                patch = mask.compile_patch(image, policies, {}, weights)
                install(changed, patch)
                if corrupt: changed.put(*corrupt)
                for m in (baseline, changed):
                    m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
                for address, size in ((OUTPUT, 32), (BOOK, 0x7E20), (MASTER, len(self.master)), (TEAM, 0x100)):
                    self.assertEqual(bytes(baseline.cpu.mem_read(address, size)), bytes(changed.cpu.mem_read(address, size)))
                self.assertEqual([baseline.reg(i) for i in range(32)], [changed.reg(i) for i in range(32)])
                self.assertEqual(baseline.cpu.reg_read(baseline.r.UC_PPC_REG_CR), changed.cpu.reg_read(changed.r.UC_PPC_REG_CR))
                self.assertEqual([baseline.fpr(i) for i in range(32)], [changed.fpr(i) for i in range(32)])
                del baseline, changed, m
                gc.collect()

    def test_pinned_reservations_exact_revert_and_receipts(self):
        for image in (self.base, self.tu):
            patch = mask.compile_patch(image, {}, {}, rows())
            audit = mask.audit_reservations(image)
            patched = bytearray(image)
            for address, value in patch.words:
                struct.pack_into('>I', patched, address-mask.IMAGE_BASE, value)
            self.assertEqual(patch.revert_image(patched), image)
            self.evidence['cases'].append({'profile': patch.profile.name, 'receipt': patch.receipt,
                'audit': audit, 'patched_sha256': hashlib.sha256(patched).hexdigest(),
                'exact_revert_sha256': hashlib.sha256(patch.revert_image(patched)).hexdigest()})
            patched[mask.HOOKS[patch.profile.name][0]-mask.IMAGE_BASE] ^= 1
            with self.assertRaisesRegex(Exception, 'word differs'): patch.revert_image(patched)


if __name__ == '__main__': unittest.main(verbosity=2)
