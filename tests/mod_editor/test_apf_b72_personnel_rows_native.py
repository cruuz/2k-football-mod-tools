"""Pinned BASE/TU execution and O-ManBlock fixture proofs. Gameplay UNWITNESSED."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_playcall_model as model
from mod_editor.core import apf2k8_situation_mask as mask
from mod_editor.core import apf2k8_splb_writer as splb
from tests.mod_editor import test_apf_playcall_research_native as native_fixture
INDEX = native_fixture.INDEX
from tests.mod_editor.test_apf_b72_personnel_rows import rows
from tools.apf_playcall_research_probe import BOOK, MASTER, MANAGER, OUTPUT, TEAM


def install(machine, policies, overrides):
    patch = mask.compile_patch(machine.image, policies, overrides)
    image = bytearray(machine.image)
    for address, value in patch.words:
        payload = struct.pack('>I', value)
        machine.cpu.mem_write(address, payload)
        image[address-mask.IMAGE_BASE:address-mask.IMAGE_BASE+4] = payload
    machine.image = bytes(image)
    return patch


class PersonnelNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_fixture.NativePlaycallTests.setUpClass.__func__(cls)

    machine = native_fixture.NativePlaycallTests.machine

    def vector(self, machine, category, row=10, category_id=6):
        captured = []
        def capture(m):
            count = m.reg(4)
            pointer, base, stride = (0x110, 0x44, 16) if category else (0xF0, 0x244, 184)
            weights = struct.unpack('>' + str(count) + 'f', m.cpu.mem_read(m.reg(3), count*4))
            captured.extend(((m.get(m.reg(1)+pointer+4*i)-MASTER-base)//stride, w) for i, w in enumerate(weights))
        machine.observers[machine.va(0x84863388)] = capture
        if category:
            machine.call(machine.va(0x8486AEB0), MANAGER, row, 0, bound=2000000)
        else:
            machine.call(machine.va(0x848693F8), MANAGER, 14, MASTER+0x44+category_id*16, 0, 0, bound=2000000)
        return tuple(captured)

    def test_every_bucket_native_factors_products_ranks_and_sums(self):
        book = self.books[130].body
        checks = 0
        for updated in (False, True):
            for down in range(1, 5):
                for yards in (1, 5, 8):
                    situation = model.Situation(down, yards, 50, 1, 900, 0, 3)
                    key = mask.situation_key(situation)
                    overrides = rows(key=key, values={'6': 10, '0': 9})
                    request = model.requested_offense_row(situation)
                    for run in (0., 1.):
                        machine = self.machine(130, updated, down=down, yards=yards, goal_yards=50, run_share=run)
                        install(machine, {}, overrides)
                        observed = self.vector(machine, True, request)
                        terms = model.category_weight_terms(book, self.master, request, situation,
                                                           run_share=run, personnel_rows=overrides['O-ManBlock'][key])
                        expected = tuple((c['category'], c['category_weight']) for c in terms)
                        self.assertEqual(observed, expected, (updated, down, yards, run))
                        self.assertEqual(sum(w for _, w in observed), sum(c['category_weight'] for c in terms))
                        for c in terms:
                            self.assertEqual(model.f32(c['curve_term']*c['ratings_term']), c['category_weight'])
                        self.assertEqual([c['rank'] for c in sorted(terms, key=lambda c: (-c['category_weight'], c['category']))], list(range(1, len(terms)+1)))
                        checks += 1
        print('PROVED exact native personnel vectors and decomposition sums for', checks, 'BASE/TU bucket/run combinations')

    def test_queens_weight_and_minimum_seven_only_formation_is_called(self):
        original = self.books[130]
        body = splb.set_formation_ratings(original.body, 14, (7, 7, 7))
        book = splb.parse_book(body, 130)
        excluded = sorted({r.formation_index for r in book.records if r.populated and r.formation_index < 151 and r.formation_index != 14})
        policies = {'O-ManBlock': [[] for _ in range(12)]}; policies['O-ManBlock'][8] = excluded
        situation = model.Situation(3, 8, 50, 1, 900, 0, 3)
        terms = model.category_weight_terms(body, self.master, 10, situation, run_share=0, personnel_rows={'6': 10})
        queens = next(c for c in terms if c['category'] == 6)
        self.assertEqual(queens['curve_term'], 1.)
        self.assertGreater(queens['category_weight'], queens['retail_weight'])
        for updated in (False, True):
            for fraction in (0., .01, .25, .5, .75, .99):
                m = self.machine(book, updated, down=3, yards=8, goal_yards=50, run_share=0, fraction=fraction)
                install(m, policies, rows())
                m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
                self.assertEqual((m.get(OUTPUT)-MASTER-0x44)//16, 6)
                self.assertEqual((m.get(OUTPUT+4)-MASTER-0x244)//184, 14)
                self.assertEqual(m.get(mask.RECEIPT_START+16), 0)
                self.assertEqual(m.get(mask.RECEIPT_START+24+16), 0)
        preview = model.predict_offense(body, self.master, 0, situation, exclusions=excluded, personnel_rows={'6': 10})
        self.assertEqual(preview.formations, [(14, model._name(self.master, 0x244+14*184), 1.)])
        print('PROVED O-ManBlock 3rd-and-8 Queens row 10:', queens)
        print('PROVED only formation 14, ratings (7,7,7), called in 12 native BASE/TU draws and all 256 model seeds')

    def test_both_draw_hooks_and_empty_fallback_keep_the_override(self):
        situation = model.Situation(3, 8, 50, 1, 900, 0, 3)
        book = self.books[130].body
        all_forms = sorted({r.formation_index for r in self.books[130].records if r.populated and r.formation_index < 151})
        for updated in (False, True):
            for excluded in ([14], [2, 24], all_forms):
                policies = {'O-ManBlock': [[] for _ in range(12)]}; policies['O-ManBlock'][8] = excluded
                for category in (True, False):
                    machine = self.machine(130, updated, down=3, yards=8, goal_yards=50, run_share=0)
                    install(machine, policies, rows())
                    actual = self.vector(machine, category)
                    if category:
                        original = model.category_weights(book, self.master, 10, situation, run_share=0, personnel_rows={'6': 10})
                        expected, fallback = mask.filter_categories(book, self.master, original, excluded)
                    else:
                        original = model.formation_weights(book, self.master, 6, situation, run_share=0)
                        expected, fallback = mask.filter_formations(original, excluded)
                    self.assertEqual(actual, expected)
                    self.assertEqual(machine.get(mask.RECEIPT_START+(0 if category else 24)+16), int(fallback))

    def test_absent_unknown_book_bucket_and_version_preserve_retail_bytes(self):
        for updated in (False, True):
            for overrides, version in (({}, None), (rows('OtherBook'), None), (rows(key=7), None), (rows(), 99)):
                original = self.machine(130, updated, down=3, yards=8, goal_yards=50)
                changed = self.machine(130, updated, down=3, yards=8, goal_yards=50)
                install(changed, {}, overrides)
                if version is not None:
                    changed.put(mask.DATA_START+4, version)
                counts = []
                for machine in (original, changed):
                    count = [0, 0]
                    for i, address in enumerate((0x84B3E858, 0x84B3E8B8)):
                        address += 0xFD0 if updated else 0
                        callback = machine.boundaries[address]
                        def counted(m, i=i, callback=callback, count=count):
                            count[i] += 1
                            return callback(m)
                        machine.boundaries[address] = counted
                    machine.call(machine.va(0x8486CE88), MANAGER, OUTPUT, stop=machine.va(0x8486D0CC), bound=2000000)
                    counts.append(count)
                self.assertEqual(counts[0], counts[1])
                for address, size in ((OUTPUT, 32), (BOOK, 0x7E20), (TEAM, 0x100), (MASTER, len(self.master))):
                    self.assertEqual(bytes(original.cpu.mem_read(address, size)), bytes(changed.cpu.mem_read(address, size)))
                self.assertEqual([original.reg(i) for i in range(32)], [changed.reg(i) for i in range(32)])
                self.assertEqual(original.cpu.reg_read(original.r.UC_PPC_REG_CR), changed.cpu.reg_read(changed.r.UC_PPC_REG_CR))
                self.assertEqual(bytes(changed.cpu.mem_read(mask.RECEIPT_START, 48)), bytes(48))
        print('PROVED retail-identical output/book/MASTER/team bytes, GPRs, CR and RNG consumption on 8 v2 bypass cases')

    def test_other_fourteen_books_have_no_policy_and_keep_identical_bytes(self):
        from mod_editor.core.apf2k8_book_identity import filename_id, read_resource
        names = ('O-ManBlock', 'O-TwoBack', 'O-SinglebackAce', 'O-Singleback3WR', 'O-WestCoast',
                 'O-ZoneBlock', 'O-Shotgun', 'X-34Base', 'X-43Cover2', 'X-43Blitz', 'X-34ZoneBlitz',
                 'USER-o', 'USER-d', 'global-o', 'global-d')
        policy = mask.decode_personnel_rows(mask.encode_data({}, rows()))
        situation = model.Situation(3, 8, 50, 1, 900, 0, 3)
        for name in names:
            resource = read_resource(INDEX, filename_id(name), 'spb', 'SPLB')
            part = resource[2].files[0].parts[0]
            body = resource[4][part.offset:part.offset+part.length]
            if name != 'O-ManBlock':
                self.assertNotIn(name, policy)
                before = model.category_weights(body, self.master, 10, situation)
                after = model.category_weights(body, self.master, 10, situation, personnel_rows=policy.get(name, [{}]*12)[8])
                self.assertEqual(before, after)
                self.assertEqual(struct.pack('>'+str(len(before))+'f', *(w for _, w in before)),
                                 struct.pack('>'+str(len(after))+'f', *(w for _, w in after)))
        print('PROVED other 14 fixture books retain exact category-weight bytes; override changes no SPLB or MASTER bytes')


if __name__ == '__main__':
    unittest.main(verbosity=2)
