"""Independent pinned PPC proof of both lotteries. Gameplay UNWITNESSED."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from collections import Counter
import gc
import hashlib
import json
import os
import struct
import unittest

from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.core import apf2k8_splb_writer as splb
from tests.mod_editor import test_apf_playcall_research_native as fixture
from tests.mod_editor import test_apf_b72_personnel_rows_native as personnel_fixture
from tests.mod_editor.test_apf_b76_situation_weights_native import install
from tools.apf_playcall_research_probe import Machine, MASTER, MANAGER, OUTPUT, BOOK, TEAM


class SituationWeightNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('APF_D3_BASE_IMAGE') and os.environ.get('APF_D3_TU_IMAGE'):
            # Optional owned caches must match the complete pinned image hashes.
            # The source XEX and MASTER still retain their independent gates.
            if hashlib.sha256(fixture.XEX.read_bytes()).hexdigest() != '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f':
                raise AssertionError('Pinned source XEX differs')
            cls.base = Path(os.environ['APF_D3_BASE_IMAGE']).read_bytes()
            cls.tu = Path(os.environ['APF_D3_TU_IMAGE']).read_bytes()
            for image, profile in zip((cls.base, cls.tu), mask.PROFILES):
                if hashlib.sha256(image).hexdigest() != profile.sha256:
                    raise AssertionError('Owned flat-image cache differs from the pinned profile')
            cls.master = fixture.read_master_play_body(fixture.INDEX)
            if hashlib.sha256(cls.master).hexdigest() != '2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891':
                raise AssertionError('Pinned MASTER differs')
            cls.books = {o: splb.read_book(fixture.INDEX, o) for o in fixture.OFFENSE + (293, 656)}
            machine = Machine(cls.base, cls.master)
            cls.initializer_result = machine.call(0x84A8AD38, MASTER, bound=16000000)
            if cls.initializer_result != 1: raise AssertionError('Native MASTER initialization failed')
            cls.runtime_master = bytes(machine.cpu.mem_read(MASTER, len(cls.master)))
        else:
            fixture.NativePlaycallTests.setUpClass.__func__(cls)
        if cls.tu is None:
            raise AssertionError('d3 requires both pinned BASE and TU profiles')
        cls.evidence = {'classification': 'PROVED OFFLINE', 'runtime_status': 'UNWITNESSED', 'cases': []}
        categories = model.category_table(cls.master)
        cls.factors = {str(r.formation_index): (.25 if r.category_index in (3, 6) else 4.)
                       for r in cls.books[130].records if r.populated and r.formation_index < 151
                       and r.category_index in (3, 6, 1, 26, 0)}
        if not cls.factors:
            raise AssertionError('Expected O-ManBlock heavy and light native categories')
        cls.weights = {'O-ManBlock': [{} for _ in range(13)]}
        cls.weights['O-ManBlock'][2] = cls.factors
        body = cls.books[130].body
        for record in cls.books[130].records:
            if record.populated and record.formation_index < 151:
                ratings = tuple((int.from_bytes(record.trailer[:4], 'big') >> shift) & 7 for shift in (14, 11)) + (2,)
                body = splb.set_formation_ratings(body, record.formation_index, ratings)
        cls.edited_book = splb.parse_book(body, 130)

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('APF_D3_WEIGHTS_RECEIPT'):
            Path(os.environ['APF_D3_WEIGHTS_RECEIPT']).write_text(json.dumps(cls.evidence, indent=2)+'\n')

    machine = fixture.NativePlaycallTests.machine

    def vector(self, m, category=True, row=4):
        return personnel_fixture.PersonnelNativeTests.vector(self, m, category, row)

    def test_native_component_values_category_means_and_final_draws(self):
        for updated in (False, True):
            image = self.tu if updated else self.base
            for run in (0., 1.):
                machines = [self.machine(self.edited_book, updated, down=1, yards=10, goal_yards=50, run_share=run) for _ in range(3)]
                for m in machines: m.normalize()
                patches = [None, mask.compile_patch(image, {}, {}, self.weights, version=3),
                           mask.compile_patch(image, {}, {}, self.weights)]
                for m, p in zip(machines, patches):
                    if p: install(m, p)
                components = [[], []]
                for i, m in enumerate((machines[0], machines[2])):
                    def capture(m, i=i):
                        components[i].append(((m.reg(28)-MASTER-0x44)//16,
                                              (m.reg(31)-MASTER-0x244)//184, m.fpr(1)))
                    m.observers[m.va(0x84869374)] = capture
                vectors = [self.vector(m) for m in machines]
                self.assertEqual(vectors[0], vectors[1], 'v3 never weighted the preceding personnel lottery')
                self.assertNotEqual(vectors[0], vectors[2])
                self.assertEqual(len(components[0]), len(components[1]))
                for (c, f, w), (cc, ff, weighted) in zip(*components):
                    self.assertEqual((c, f), (cc, ff))
                    self.assertEqual(weighted, model.f32(w*self.factors.get(str(f), 1.)))
                situation = model.Situation(1, 10, 50, 1, 900, 0, 3)
                expected = model.category_weights(self.edited_book.body, self.master, 4, situation,
                                                 run_share=run, formation_multipliers=self.factors)
                self.assertEqual(vectors[2], expected)
                # Final Queens relative weights are unchanged by their uniform
                # .25 factor; v4 now also changes the earlier personnel choice.
                before = self.vector(machines[0], False)
                after = self.vector(machines[2], False)
                self.assertEqual(after, tuple((f, model.f32(w*.25)) for f, w in before))
                for m in machines: m.observers.clear()
                calls = [[], [], []]
                for i in range(24):
                    for j, m in enumerate(machines):
                        m.configure(down=1, yards=10, goal_yards=50, run_share=run, fraction=(i+.5)/24)
                        m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
                        calls[j].append(((m.get(OUTPUT)-MASTER-0x44)//16, (m.get(OUTPUT+4)-MASTER-0x244)//184))
                self.assertEqual(calls[0], calls[1])
                self.assertNotEqual(calls[0], calls[2])
                self.evidence['cases'].append({'profile': patches[2].profile.name, 'run': run,
                    'factors': self.factors, 'category_vectors': vectors, 'category_components': components,
                    'cpu_calls_per_revision': len(calls[0]),
                    'cpu_counts': [dict(Counter(str(v) for v in arm)) for arm in calls]})
                del machines
                gc.collect()

    def test_other_bucket_and_book_missing_corrupt_policy_preserve_native(self):
        for updated in (False, True):
            image = self.tu if updated else self.base
            for book, down, yards, corrupt in ((130, 1, 5, None), (130, 3, 8, None), (767, 1, 10, None),
                                              (130, 1, 10, (mask.DATA_START+4, 99)),
                                              (130, 1, 10, (mask.DATA_START+16+288+4, 0xFFFFFFFF))):
                original = self.machine(book, updated, down=down, yards=yards, goal_yards=50, run_share=0)
                changed = self.machine(book, updated, down=down, yards=yards, goal_yards=50, run_share=0)
                install(changed, mask.compile_patch(image, {}, {}, self.weights))
                if corrupt: changed.put(*corrupt)
                self.assertEqual(self.vector(original, True, 25), self.vector(changed, True, 25),
                                 'Wildcard category requests retain their native weights')
                for m in (original, changed):
                    m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
                for address, size in ((OUTPUT, 32), (BOOK, 0x7E20), (MASTER, len(self.master)), (TEAM, 0x100)):
                    self.assertEqual(bytes(original.cpu.mem_read(address, size)), bytes(changed.cpu.mem_read(address, size)))
                self.assertEqual([original.reg(i) for i in range(32)], [changed.reg(i) for i in range(32)])
                self.assertEqual([original.fpr(i) for i in range(32)], [changed.fpr(i) for i in range(32)])
                self.assertEqual(original.cpu.reg_read(original.r.UC_PPC_REG_CR), changed.cpu.reg_read(changed.r.UC_PPC_REG_CR))
                del original, changed, m
                gc.collect()

    def test_reservations_and_exact_revert_both_profiles(self):
        for image in (self.base, self.tu):
            patch = mask.compile_patch(image, {}, {}, self.weights)
            audit = mask.audit_reservations(image)
            changed = bytearray(image)
            for address, value in patch.words: struct.pack_into('>I', changed, address-mask.IMAGE_BASE, value)
            self.assertEqual(patch.revert_image(changed), image)
            self.evidence['cases'].append({'profile': patch.profile.name, 'audit': audit,
                'receipt': patch.receipt, 'patched_sha256': hashlib.sha256(changed).hexdigest()})


if __name__ == '__main__': unittest.main(verbosity=2)
