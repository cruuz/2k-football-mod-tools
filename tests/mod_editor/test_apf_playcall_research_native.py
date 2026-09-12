"""Pinned, bounded offensive-call witnesses. No retail fixtures or outputs.

Standalone: PYTHONPATH=. python3 tests/mod_editor/test_apf_playcall_research_native.py
APF_RETAIL_XEX, APF_RETAIL_TU and APF_RETAIL_INDEX override owned input paths.
The retail-only setup derives both images in memory and runs MASTER's native
relocator/validator. Missing retail or optional native libraries causes SkipTest.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import apf2k8_xex as xex
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core.apf2k8_playcall_patch import PROFILES
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
from tools.apf_playcall_research_probe import (
    Machine, BOOK, MASTER, MANAGER, STATE, TEAM, GAME, HISTORY, OUTPUT,
)

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)')
XEX = Path(os.environ.get('APF_RETAIL_XEX', str(RETAIL / 'default.xex')))
INDEX = Path(os.environ.get('APF_RETAIL_INDEX', str(RETAIL / '0A')))
TU = Path(os.environ.get('APF_RETAIL_TU', '/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082'))
OFFENSE = (130, 259, 369, 767, 891, 943, 1411, 1037, 1439)


def heavy_addition(book, donor):
    changes = []
    first = next(r.record_index for r in book.records if not r.populated)
    for slot, formation in ((first, 9), (first + 1, 5)):
        record = next(r for r in donor.records if r.populated and r.formation_index == formation)
        changes.extend(splb.MembershipChange(book.outer_index, slot, e.play_index, True)
                       for e in record.entries)
        changes.append(splb.TrailerReplace(book.outer_index, slot, formation, record.category_index))
    compiled = splb.compile_book(book, changes)
    splb.verify_book(book.body, compiled.replacement, changes)
    return splb.parse_book(compiled.replacement, book.outer_index)


def category_candidates(machine, row):
    candidates = []
    def capture(m):
        sp = m.reg(1)
        for i in range(m.reg(24)):
            category = (m.get(sp + 0x110 + i * 4) - MASTER - 0x44) // 16
            weight = struct.unpack('>f', m.cpu.mem_read(sp + 0x70 + i * 4, 4))[0]
            candidates.append((category, weight))
    address = machine.va(0x8486B198)
    machine.observers[address] = capture
    result = machine.call(machine.va(0x8486AEB0), MANAGER, row, 0)
    del machine.observers[address]
    return ((result - MASTER - 0x44) // 16 if result else None), candidates


class NativePlaycallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import capstone  # noqa: F401
            import unicorn  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(f'Optional native research dependency absent: {exc}')
        for path, variable in ((XEX, 'APF_RETAIL_XEX'), (INDEX, 'APF_RETAIL_INDEX')):
            if not path.is_file():
                raise unittest.SkipTest(f'Owned retail input absent: {path}; set {variable}')
        source = XEX.read_bytes()
        if hashlib.sha256(source).hexdigest() != '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f':
            raise AssertionError('Existing APF_RETAIL_XEX is not the pinned BASE input')
        cls.base, cls.base_receipt = xex.decode_xex(source)
        assert hashlib.sha256(cls.base).hexdigest() == PROFILES[0].sha256
        cls.tu = None
        if TU.is_file():
            cls.tu, cls.tu_receipt = xex.reconstruct_tu(cls.base, source, TU.read_bytes())
            assert hashlib.sha256(cls.tu).hexdigest() == PROFILES[1].sha256
        cls.master = read_master_play_body(INDEX)
        assert hashlib.sha256(cls.master).hexdigest() == '2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891'
        cls.books = {o: splb.read_book(INDEX, o) for o in OFFENSE + (293, 656)}
        cls.added = heavy_addition(cls.books[767], cls.books[1411])
        machine = Machine(cls.base, cls.master)
        cls.initializer_result = machine.call(0x84A8AD38, MASTER, bound=16000000)
        cls.initializer_steps = machine.steps
        cls.runtime_master = bytes(machine.cpu.mem_read(MASTER, len(cls.master)))
        print(f'PROVED MASTER native relocation/validation: result={cls.initializer_result}; instructions={cls.initializer_steps}', flush=True)

    def machine(self, book=767, updated=False, **state):
        if updated and self.tu is None:
            self.skipTest(f'Owned TU 1.1 input absent: {TU}; set APF_RETAIL_TU')
        m = Machine(self.tu if updated else self.base, self.runtime_master)
        m.install(self.books[book] if isinstance(book, int) else book)
        m.configure(**state)
        return m

    def test_master_initialization_enables_all_retail_plays(self):
        self.assertEqual(self.initializer_result, 1)
        self.assertLess(self.initializer_steps, 16000000)
        self.assertEqual(sum(bool(struct.unpack_from('>I', self.runtime_master, 0x80CC + i * 100)[0] & 0x80000)
                             for i in range(586)), 586)

    def test_resource_names_and_filename_hashes(self):
        from mod_editor.core.apf2k8_book_identity import filename_id
        archive = splb.apf_outer.parse_archive(INDEX)
        for outer, name in ((293, 'USER-d'), (656, 'global-d'), (1037, 'USER-o'), (1439, 'global-o')):
            self.assertEqual(self.books[outer].name, name)
            self.assertEqual(archive.entries[outer].name_id, filename_id(name))

    def test_goal_line_compiled_heavy_categories_survive_normalizer(self):
        m = self.machine(self.added)
        normalized = splb.parse_book(m.normalize(), 767)
        self.assertEqual(splb.book_category_rows(normalized.body), (0, 1, 2, 5, 8))
        self.assertEqual([r.formation_index for r in normalized.records[27:29]], [9, 5])
        self.assertEqual([int.from_bytes(r.trailer[4:], 'big') for r in normalized.records[27:29]], [1, 2])
        # Both choices are real: lower RNG quantile Jacks, middle quantile Jokers.
        for fraction, expected in ((0.01, 0), (0.5, 1)):
            m.configure(fraction=fraction)
            row = m.call(m.va(0x84867600))
            self.assertEqual(row, 0)
            category, weights = category_candidates(m, row)
            self.assertEqual(category, expected)
            self.assertGreater(dict(weights)[0], 0)
            self.assertGreater(dict(weights)[1], 0)
        print('PROVED compiled/normalized heavy GL candidates:', weights, flush=True)
        stock_category, _ = category_candidates(self.machine(767), 0)
        self.assertEqual(stock_category, 2)
        native_category, native_weights = category_candidates(self.machine(1411), 0)
        self.assertEqual(native_category, 1)
        self.assertAlmostEqual(dict(native_weights)[0], 0.91, places=6)
        self.assertAlmostEqual(dict(native_weights)[1], 0.91, places=6)

    def test_whole_offensive_call_selects_added_heavy_without_fetch_or_ladder(self):
        m = self.machine(self.added, run_share=0, fraction=0.5)
        m.normalize()
        m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
        category, formation, play = (m.get(OUTPUT + i) for i in (0, 4, 12))
        self.assertEqual(category, MASTER + 0x54)
        self.assertEqual(formation, MASTER + 0x244 + 5 * 184)
        self.assertTrue(MASTER + 0x80C4 <= play < MASTER + 0x80C4 + 586 * 100)
        self.assertIn(m.va(0x8486B2D0), m.visited)
        self.assertNotIn(m.va(0x848699D8), m.visited)
        self.assertNotIn(m.va(0x84860730), m.visited)
        self.assertNotIn(m.va(0x84A8AA80), m.visited)
        print('PROVED complete GL call:', (category - MASTER - 0x44) // 16,
              (formation - MASTER - 0x244) // 184, (play - MASTER - 0x80C4) // 100, flush=True)

    def test_third_down_requests_and_category_weights(self):
        m = self.machine(goal_yards=50)
        expected = {130: (1, 6, 6), 767: (2, 8, 8), 1411: (3, 7, 7), 1037: (2, 8, 8), 1439: (1, 7, 7)}
        rows = []
        for ordinal, yards in enumerate((3, 8, 15)):
            m.configure(down=3, yards=yards, goal_yards=50)
            row = m.call(m.va(0x84867600))
            rows.append(row)
            for outer in expected:
                m.install(self.books[outer])
                result, weights = category_candidates(m, row)
                self.assertEqual(result, expected[outer][ordinal], (outer, yards, weights))
                self.assertNotIn(m.va(0x84860730), m.visited)
        self.assertEqual(rows, [4, 10, 10])
        print('PROVED neutral 3rd-down rows:', rows, 'category choices:', expected, flush=True)

    def test_ladder_is_a_separate_bounded_lineup_resolver(self):
        m = self.machine(130)
        observed = []
        for row in range(28):
            m.call(m.va(0x84860730), 0x123456, row, 0, stop=m.va(0x8486088C))
            pointer = m.reg(31)
            got = (pointer - MASTER - 0x44) // 16 if pointer else None
            expected = splb.personnel_category_for_row(self.books[130], row)
            self.assertEqual(got, expected)
            observed.append(got)
        self.assertEqual(observed[8:11], [6, 6, 6])

    def test_third_down_full_call_tuples_and_te_counts(self):
        expected = {
            130: ((1, 27, 42), (6, 14, 114), (6, 14, 114)),
            767: ((2, 91, 78), (8, 92, 78), (8, 92, 78)),
            1411: ((3, 119, 114), (7, 133, 216), (7, 133, 216)),
        }
        for outer, triples in expected.items():
            for yards, triple in zip((3, 8, 15), triples):
                m = self.machine(outer, down=3, yards=yards, goal_yards=50, run_share=0)
                m.call(0x8486CE88, MANAGER, OUTPUT, stop=0x8486D0CC, bound=2000000)
                actual = tuple((m.get(OUTPUT + d) - MASTER - offset) // stride
                               for d, offset, stride in ((0, 0x44, 16), (4, 0x244, 184), (12, 0x80C4, 100)))
                self.assertEqual(actual, triple)
                self.assertNotIn(0x84860730, m.visited)
        print('PROVED third-down category/formation/play tuples:', expected, flush=True)

    def test_removed_record_hides_suffix_then_normalizer_compacts_it(self):
        body = bytearray(self.books[767].body)
        body[0x70:0x118] = struct.pack('>H', splb.FILLER) * 84
        removed = splb.parse_book(bytes(body), 767)
        m = self.machine(removed)
        formation = lambda i: MASTER + 0x244 + i * 184
        self.assertEqual(m.call(m.va(0x84A8A258), BOOK, formation(68)), 0)
        self.assertEqual(m.call(m.va(0x84A8A258), BOOK, formation(69)), 0)
        self.assertEqual(m.call(m.va(0x84A89E08), BOOK, 0), 0)
        with self.assertRaisesRegex(AssertionError, '84A8C5C8'):
            m.call(m.va(0x84A8C5B0), BOOK, formation(68))
        after = splb.parse_book(m.normalize(), 767)
        self.assertEqual(after.records[0].formation_index, 69)
        self.assertNotIn(68, [r.formation_index for r in after.records if r.populated])
        self.assertEqual(m.call(m.va(0x84A8A258), BOOK, formation(68)), 0)
        self.assertEqual(m.call(m.va(0x84A8A258), BOOK, formation(69)), BOOK + 0x70)

    def test_mask_only_retirement_is_rebuilt(self):
        m = self.machine(767)
        m.put(BOOK + 0x7E04, 0)
        m.normalize()
        self.assertEqual(m.get(BOOK + 0x7E04), 0x124)

    def test_user_and_global_books_enter_same_native_selector(self):
        for outer in (1037, 1439):
            m = self.machine(outer, run_share=0)
            m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
            self.assertTrue(m.get(OUTPUT))
            self.assertIn(m.va(0x8486C930), m.visited)
            self.assertIn(m.va(0x8486AEB0), m.visited)
            if outer == 1037:
                self.assertTrue(m.get(OUTPUT + 4))
                self.assertTrue(m.get(OUTPUT + 12))
                self.assertIn(m.va(0x8486B2D0), m.visited)
            else:
                # global-o is a seven-record special-play book. Directly
                # assigning it does not make its hidden records ordinary sets.
                self.assertEqual(m.get(OUTPUT + 4), 0)
                self.assertEqual(m.get(OUTPUT + 12), 0)
                self.assertIn(m.va(0x848699D8), m.visited)
                m.normalize()
                m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
                self.assertEqual((m.get(OUTPUT + 4), m.get(OUTPUT + 12)), (0, 0))

    def test_user_global_and_cpu_labels_take_common_filename_branch(self):
        for name in ('O-ManBlock', 'USER-o', 'global-o'):
            m = self.machine()
            m.cpu.mem_write(0x3B0000, name.encode('utf-16-be') + bytes(2))
            m.put(0x3A0004, 0x3B0000)
            m.setreg(30, 0x3A0000)
            # Enter with the already resolved label; stop at formatter inputs.
            m.call(0x849D6270, stop=0x849D64B8)
            self.assertEqual(m.reg(11), 0x3B0000)
            self.assertEqual(m.reg(5), 0x845F1764)  # {0}-spb.iff
            self.assertIn(0x849D6490, m.visited)

    def test_dispatch_tables_are_family_and_match_phase_switches(self):
        expected13 = [0x8486C9DC] * 4 + [0x8486CAC4] * 4 + [0x8486C9BC, 0x8486CAC4, 0x8486C9B4, 0x8486CAC4, 0x8486CA70]
        expected4 = [0x8486CA1C, 0x8486CA24, 0x8486CA60, 0x8486CA80]
        for base_address, expected in ((0x8486C980, expected13), (0x8486CA0C, expected4)):
            self.assertEqual(list(struct.unpack_from(f'>{len(expected)}I', self.base, base_address - 0x82000000)), expected)

    def test_wrapper_passes_the_staging_output_and_obeys_busy_flag(self):
        m = self.machine()
        staging = 0x85158350
        m.put(0x84F3F8F8, 5)
        m.call(0x84815608, MANAGER, stop=0x8486CE88)
        self.assertEqual(m.reg(4), staging + 0x10)
        self.assertEqual(m.get(staging), 1)
        self.assertEqual(bytes(m.cpu.mem_read(staging + 0x10, 20)), bytes(20))
        m.call(0x84815608, MANAGER)
        self.assertNotIn(0x8486CE88, m.visited)

    def test_dispatch_executes_family_and_phase_rows(self):
        m = self.machine(1411)
        seen = []
        # Stop after dispatch, before category enumeration. The dispatch itself
        # is native; a synthetic formation provides each switch index.
        m.observers[0x8486CA88] = lambda z: seen.append(z.reg(31))
        for family, row in ((0, 25), (1, 25), (2, 25), (3, 25), (8, 21), (10, 17), (12, 19)):
            m.put(0x3A0000, 0x845EBB14)  # pinned UTF-16 "Kickoff"
            m.put(0x3A0004, family << 26)
            m.call(0x8486C930, 0x3A0000, stop=0x8486CA88)
            # Unicorn stops before the observer at the end address.
            self.assertEqual(m.reg(31), row)
        m.put(0x3A0000, 0x845EBB16)  # unequal name => onside row 22
        m.put(0x3A0004, 8 << 26)
        m.call(0x8486C930, 0x3A0000, stop=0x8486CA88)
        self.assertEqual(m.reg(31), 22)
        for family in (4, 5, 6, 7, 9, 11, 13):
            m.put(0x3A0004, family << 26)
            self.assertEqual(m.call(0x8486C930, 0x3A0000), 0)
        for phase, row in ((1, 21), (2, 21), (3, 19), (4, 0)):
            m.put(GAME + 0x34, phase)
            m.call(0x8486C930, 0, stop=0x8486CA88)
            self.assertEqual(m.reg(31), row)
        for phase in (0, 5):
            m.put(GAME + 0x34, phase)
            self.assertEqual(m.call(0x8486C930, 0), 0)

    def test_team_slider_conversion_and_situation_adjustment(self):
        from mod_editor.core.apf2k8_book_identity import read_disc_roster
        import apf_roster
        roster = read_disc_roster(INDEX)
        tables, _ = apf_roster.parse_root(roster)
        team, tendency = tables[4], tables[9]
        self.assertEqual((team.stride, tendency.stride, tendency.count), (384, 180, 42))
        for i in range(team.count):
            pointer = team.offset + team.stride * i + 0xF8
            target = pointer + struct.unpack_from('>i', roster, pointer)[0] - 1
            self.assertEqual((target - tendency.offset) % tendency.stride, 0)
            self.assertTrue(tendency.offset <= target < tendency.offset + tendency.count * tendency.stride)
        self.assertTrue(all(not any(roster[tendency.offset + i * 180 + 0x8E:
                                                 tendency.offset + i * 180 + 0xA4])
                            for i in range(tendency.count)))
        m = self.machine(goal_yards=50)
        source = bytearray(roster[tendency.offset:tendency.offset + tendency.stride])
        m.put(TEAM, 0x3A0000)
        for slider in (0, 50, 100):
            source[0x5A] = slider
            m.cpu.mem_write(0x3B0000, bytes(source))
            m.call(0x8492A440, 0x3A0000, 0x3B0000)
            self.assertEqual(struct.unpack('>2H', m.cpu.mem_read(0x3A0000, 4)), (100 - slider, slider))
            for source_offset, working_offset in ((0x8E, 0x9E), (0x99, 0xB4)):
                self.assertEqual(struct.unpack('>11H', m.cpu.mem_read(0x3A0000 + working_offset, 22)),
                                 tuple(source[source_offset:source_offset + 11]))
        adjusted = []
        for yards in (3, 8, 15):
            m.configure(down=3, yards=yards, goal_yards=50)
            m.setfpr(1, 0.5)
            m.call(0x8486A1F8)
            adjusted.append(m.fpr(1))
        self.assertAlmostEqual(adjusted[0], 0.45, places=6)
        self.assertEqual(adjusted[1:], [0.0, 0.0])
        print('PROVED slider 0.5 adjusted on neutral third downs:', adjusted, flush=True)

        # Run the real tendency preparation through its Bernoulli choice.
        # These retail records have zero explicit row arrays, so the optional
        # category/formation cache remains invalid, but its run/pass draw lives.
        for slider, expected in ((0, 0.0), (50, 1.0), (100, 1.0)):
            m.configure(down=1, yards=10, goal_yards=50)
            source[0x5A] = slider
            m.cpu.mem_write(0x3B0000, bytes(source))
            m.call(0x8492A440, 0x3A0000, 0x3B0000)
            intermediate = []
            m.observers[0x84929B28] = lambda z: intermediate.append(z.fpr(1))
            m.call(0x84929A48, bound=500000)
            m.call(0x8492A2A8)
            self.assertEqual(intermediate, [slider / 100])
            self.assertEqual(m.fpr(1), expected)
            self.assertFalse(m.get(0x8519A71C) & 0x80000000)

    def test_x_rating_is_independent_of_y_audible_slot(self):
        m = self.machine(767)
        record = self.books[767].records[0]
        entry = record.entries[0]
        formation = MASTER + 0x244 + record.formation_index * 184
        play = MASTER + 0x80C4 + entry.play_index * 100
        for x in range(5):
            for y in range(5):
                m.cpu.mem_write(BOOK + 0x70, struct.pack('>H', (x << 13) | (y << 10) | entry.play_index))
                self.assertEqual(m.call(0x84A8B2B0, BOOK, formation, play), x)

    def test_master_category_rows_and_te_roles_are_distinct_namespaces(self):
        for category, row in enumerate(splb.PERSONNEL_ROWS):
            self.assertEqual(self.runtime_master[0x44 + category * 16 + 4] & 63, row)
        roles = lambda c: [b & 31 for b in self.runtime_master[0x49 + c * 16:0x54 + c * 16]]
        self.assertEqual([roles(c).count(8) for c in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 26)], [3, 2, 2, 1, 2, 1, 0, 1, 0, 0, 2])
        expected = {130: (0, 1, 3, 6, 26), 259: (0, 1, 3, 6, 26),
                    369: (0, 1, 2, 8), 767: (2, 5, 8), 891: (0, 1, 3, 6, 26),
                    943: (0, 2, 3, 5, 8), 1411: (0, 1, 2, 3, 5, 6, 7, 8, 9),
                    1037: (0, 1, 2, 3, 5, 6, 7, 8), 1439: (1, 7, 15, 17, 19, 20)}
        self.assertEqual({o: splb.book_category_rows(self.books[o].body) for o in OFFENSE}, expected)
        global_forms = [r.formation_index for r in self.books[1439].records if r.populated]
        self.assertEqual(global_forms, list(range(151, 158)))
        self.assertEqual([struct.unpack_from('>I', self.runtime_master, 0x244 + i * 184 + 8)[0] & 1
                          for i in global_forms], [1, 1, 0, 0, 0, 0, 1])

    def test_four_retries_keep_the_formation_and_do_not_advance_a_row(self):
        m = self.machine(self.added, run_share=0)
        # A real runtime validity input: clear all validation bits in MASTER.
        # No candidate is eligible; observe the real loop and its emergency fetch.
        for i in range(586):
            address = MASTER + 0x80CC + i * 100
            m.put(address, m.get(address) & ~0x80000)
        tries = []
        m.observers[m.va(0x8486CF84)] = lambda z: tries.append((z.reg(25), z.reg(3)))
        m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
        self.assertEqual([i for i, _ in tries], [0, 1, 2, 3])
        self.assertEqual(tries[0][1], 0)
        self.assertTrue(tries[1][1])
        self.assertEqual(len({f for _, f in tries[1:]}), 1)
        self.assertIn(m.va(0x848699D8), m.visited)
        self.assertEqual(m.get(OUTPUT + 12), 0)

    def test_tu_goal_line_and_third_down_native(self):
        m = self.machine(self.added, updated=True, run_share=0)
        m.normalize()
        m.call(m.va(0x8486CE88), MANAGER, OUTPUT, stop=m.va(0x8486D0CC), bound=2000000)
        self.assertEqual(m.get(OUTPUT), MASTER + 0x54)
        self.assertEqual(m.get(OUTPUT + 4), MASTER + 0x244 + 5 * 184)
        self.assertTrue(m.get(OUTPUT + 12))
        for yards, expected in ((3, 4), (8, 10), (15, 10)):
            m.configure(down=3, yards=yards, goal_yards=50)
            self.assertEqual(m.call(m.va(0x84867600)), expected)

    def test_complete_static_difference_receipt(self):
        if self.tu is None:
            self.skipTest('Owned TU absent; two-image disassembly requires both images')
        import json
        from tools.apf_playcall_research_evidence import evidence
        path = Path(__file__).resolve().parents[2] / 'docs/research/apf_playcall_b67_evidence.json'
        self.assertEqual(evidence(self.base, self.tu), json.loads(path.read_text()))
        # The family-zero cutoff uses another literal pool cell, same value.
        self.assertEqual(self.base[0xB4544:0xB4548], self.tu[0x17DB8:0x17DBC])

    def test_tu_prefers_valid_primary_category_in_nearby_resolver(self):
        for updated, pc, expected in ((False, 0x84864AB8, 2), (True, 0x84865758, 5)):
            m = self.machine(767, updated=updated)
            result = m.call(pc, BOOK, MASTER + 0x244 + 72 * 184)
            self.assertEqual(result, MASTER + 0x44 + expected * 16)
        for updated, pc, stop, expected in ((False, 0x84867938, 0x84867A3C, 2),
                                            (True, 0x84868608, 0x8486873C, 5)):
            m = self.machine(767, updated=updated)
            record = next(r for r in self.books[767].records if r.populated and r.formation_index == 72)
            play = MASTER + 0x80C4 + record.entries[0].play_index * 100
            m.call(pc, MANAGER, 0, MASTER + 0x244 + 72 * 184, play, play, 0, stop=stop)
            self.assertEqual(m.reg(31), MASTER + 0x44 + expected * 16)

    def test_audible_y_lookup_is_separate_from_initial_x_weight(self):
        m = self.machine(767)
        record = self.books[767].records[0]
        formation = MASTER + 0x244 + record.formation_index * 184
        for slot in range(4):
            expected = next(e.play_index for e in record.entries if e.y == slot)
            self.assertEqual(m.call(0x84A8AA80, BOOK, formation, slot), MASTER + 0x80C4 + expected * 100)


if __name__ == '__main__':
    unittest.main(verbosity=2)
