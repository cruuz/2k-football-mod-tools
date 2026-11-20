"""Slices 2 and 3 code module: generated template, installer tables, weekly edit and the frozen slice 1 and 2 modules.

pos2/DESIGN.md and pos3/DESIGN.md section 6 test 3. Native behaviour is in test_b81_sim_pos_injuries_native.py.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from mod_editor.core import nfl2k5_sim_qb_injuries_code as rules
from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice1 as frozen
from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice2 as frozen2
from mod_editor.core import nfl2k5_sim_rb_injuries as running_backs
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import retail_bytes


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / 'tools/qb_sim_injuries'
BANK, SIM, DATA, LINEUP, RB = 0x1524000, 0x150E000, 0x14FD650, 0x151CE00, 0x1519A80
# The bytes of `git show d8ceb91e3:mod_editor/core/nfl2k5_sim_qb_injuries_code.py` (sha256sum of that output).
SLICE1_SHA256 = 'ab914dbc3989ecaf33799f95c0e555027c2ae097758e97b425b655227ceded3c'
# The bytes of `git show d2abd00a5:mod_editor/core/nfl2k5_sim_qb_injuries_code.py`, the refit slice 2 head slice 3 extends.
SLICE2_SHA256 = '392af556f5f034cc72da325931885b7a5b109f34d3e7112a8c5792b8f7e23329'
# The only template bytes that differ from the frozen slice 2 template: inside the positions piece, which now ends at
# 0x1AF5 (slice 2's ended at 0x1B39; the rest of both is 0xCC fill up to 0x2000).
CHANGED_FROM_SLICE2 = (0x1402, 0x1B39)
POSITIONS_END = 0x1AF5
# Template ranges that differ from the frozen slice 1 template (pos2/DESIGN_CHANGES.md 2): clinical from its first
# reference to a label after `finished` to its end, the new positions piece, and fixture_start and context, where the
# added line lengthens the jumps that cross it.
CHANGED = ((0xFB, 0x13B0), (0x1400, POSITIONS_END), (0x310C, 0x31AB), (0x361B, 0x3828))
FINISHED = 0x21E
ADDED_LINES = {'clinical.S': '    call POSITIONS', 'context.S': '    mov dword ptr [POS_CACHED_YEAR],-1',
               'fixture_start.S': '    mov dword ptr [POS_CACHED_YEAR],-1'}
# pos2/DESIGN.md section 2 and pos3/DESIGN.md section 1: class, side (0 offense, 1 defense), lineup slot, flags
# (bits 0-1 the rule: 0 every scrimmage play, 1 rushing ball carrier, 2 rush play; bits 4-7 the weight in sixteenths).
SLOTS = ((0, 0, 12, 0), (0, 0, 13, 0), (1, 0, 10, 0), (1, 0, 11, 0), (2, 0, 9, 0), (3, 1, 15, 0), (3, 1, 16, 0),
         (4, 0, 1, 1), (4, 0, 3, 1),
         (5, 0, 4, 0), (5, 0, 5, 0), (5, 0, 6, 0), (5, 0, 7, 0x40), (6, 0, 8, 0), (7, 0, 2, 0x02), (8, 1, 17, 0),
         (8, 1, 18, 0), (9, 1, 19, 0), (9, 1, 20, 0), (9, 1, 21, 0), (9, 1, 22, 0x40), (10, 1, 24, 0),
         (10, 1, 25, 0), (10, 1, 26, 0), (11, 1, 23, 0), (11, 1, 27, 0), (11, 1, 28, 0x40))
# pos3/DESIGN.md section 2: weeks 0-1, 2, 3, 4-7, 8-15, 16-31.
WEEK_GROUPS = (0, 0, 1, 2) + (3,) * 4 + (4,) * 8 + (5,) * 16


def _toolchain():
    if not all(shutil.which(tool) for tool in ('gcc', 'as', 'ld')) or not importlib.util.find_spec('elftools'):
        raise unittest.SkipTest('development build needs GNU i386 gcc/binutils and pyelftools')
    version = subprocess.run(['gcc', '-dumpfullversion'], capture_output=True, text=True)
    assembler = subprocess.run(['as', '--version'], capture_output=True, text=True)
    if version.stdout.strip() != '13.3.0' or '2.42' not in assembler.stdout.partition('\n')[0]:
        raise unittest.SkipTest('the checked-in i386 template was generated with GCC 13.3 and GNU binutils 2.42')


def _build_module():
    spec = importlib.util.spec_from_file_location('qb_sim_injuries_build_probe', TOOLS / 'build.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GeneratedTemplate(unittest.TestCase):
    def test_build_check_passes_and_slice_1_sources_changed_only_by_the_three_added_lines(self):
        _toolchain()
        subprocess.run([sys.executable, str(TOOLS / 'build.py'), '--check'], check=True)
        # The current sources without the call at `finished`, the two cache lines and the positions piece
        # regenerate the frozen slice 1 template, relocations and labels byte for byte.
        build = _build_module()
        self.assertIn(('positions', 0x1400), build.PIECES)
        with tempfile.TemporaryDirectory(prefix='2k5-slice1-') as folder:
            folder = Path(folder)
            for source in TOOLS.iterdir():
                if source.suffix in ('.S', '.c') and source.name != 'positions.S':
                    shutil.copy(source, folder / source.name)
            for name, line in ADDED_LINES.items():
                lines = (folder / name).read_text().split('\n')
                found = [n for n, text in enumerate(lines) if text.split('#')[0].rstrip() == line]
                self.assertEqual(len(found), 1, name)
                del lines[found[0]]
                (folder / name).write_text('\n'.join(lines))
            build.HERE = folder
            build.PIECES = tuple(piece for piece in build.PIECES if piece[0] != 'positions')
            for name in ('POSITIONS', 'POS_CACHED_YEAR', 'QB_PRIVATE_RNG'):
                del build.LOCAL[name]
            del build.EXPORTED['positions']
            generated = build.render()
        text = Path(frozen.__file__).read_text(encoding='utf-8')
        self.assertEqual(text[text.index(build.DIVIDER):], generated)

    def test_template_differs_from_slice_1_only_in_the_stated_ranges_inside_the_same_allocation(self):
        self.assertEqual(space.QB_INJURY_REQUEST, ('nfl2k5_sim_qb_injuries', 'code', 0x4000, 0x1000))
        self.assertEqual(rules.CODE_SIZE, space.QB_INJURY_REQUEST[2])
        old, new = frozen._TEMPLATE, rules._TEMPLATE
        self.assertEqual((len(old), len(new)), (rules.CODE_SIZE, frozen.CODE_SIZE))
        differ = [n for n in range(len(new)) if old[n] != new[n]]
        inside = lambda n: any(start <= n < end for start, end in CHANGED)
        self.assertEqual([hex(n) for n in differ if not inside(n)], [])
        for start, end in CHANGED:
            here = [n for n in differ if start <= n < end]
            self.assertEqual((here[0], here[-1] + 1), (start, end), hex(start))
        # Before `finished` only 4-byte fields change: call displacements and relocated addresses of moved labels.
        fields = {offset for offset, *_ in frozen._RELOCATIONS}
        fields |= {n + 1 for n in range(FINISHED) if old[n] == 0xE8}
        for n in differ:
            if n < FINISHED:
                self.assertTrue(any(field <= n < field + 4 for field in fields), hex(n))
        self.assertEqual(rules.LABELS['finished'], frozen.LABELS['finished'])
        linked = rules._link_authored(BANK, SIM, DATA, LINEUP + 0x455)
        self.assertEqual(linked[FINISHED:FINISHED + 5], b'\xe8' + struct.pack('<i', 0x1400 - FINISHED - 5))
        # The positions piece ends before the recovery piece at 0x2000, followed only by fill.
        self.assertEqual(rules.LABELS['positions'], 0x1400)
        self.assertEqual(new[POSITIONS_END:0x2000], b'\xcc' * (0x2000 - POSITIONS_END))
        self.assertEqual(old[0x13A8:0x2000], b'\xcc' * (0x2000 - 0x13A8))
        unmoved = {name for name, at in frozen.LABELS.items() if at < FINISHED or 0x2000 <= at < 0x3100
                   or 0x3200 <= at < 0x3600 or at >= 0x3840}
        self.assertEqual({name: rules.LABELS[name] for name in unmoved}, {name: frozen.LABELS[name] for name in unmoved})
        self.assertEqual(set(frozen.LABELS) - set(rules.LABELS), set())

    def test_template_equals_the_frozen_slice_2_template_outside_the_positions_piece(self):
        old, new = frozen2._TEMPLATE, rules._TEMPLATE
        differ = [n for n in range(len(new)) if old[n] != new[n]]
        self.assertEqual((differ[0], differ[-1] + 1), CHANGED_FROM_SLICE2)
        self.assertEqual({name: at for name, at in rules.LABELS.items() if not 0x1400 <= at < 0x2000},
                         {name: at for name, at in frozen2.LABELS.items() if not 0x1400 <= at < 0x2000})
        self.assertEqual(set(rules.LABELS) - set(frozen2.LABELS), {'pos_week_group'})
        # Outside the piece, relocations are slice 2's; the only target that moved is pos_year, which context.S and
        # fixture_start.S clear on a re-entered fixture (its value is the label's bank offset).
        moved = {('bank', frozen2.LABELS['pos_year']): ('bank', rules.LABELS['pos_year'])}
        self.assertEqual([r for r in rules._RELOCATIONS if not 0x1400 <= r[0] < 0x2000],
                         [r[:2] + moved.get(r[2:], r[2:]) for r in frozen2._RELOCATIONS if not 0x1400 <= r[0] < 0x2000])
        self.assertEqual(sum(r[2:] in moved for r in frozen2._RELOCATIONS if not 0x1400 <= r[0] < 0x2000), 2)
        self.assertEqual(rules._LOCAL_FUNCTIONS, frozen2._LOCAL_FUNCTIONS)
        end = 0x2000
        while new[end - 1] == 0xCC:
            end -= 1
        self.assertEqual(end, POSITIONS_END)
        self.assertLess(POSITIONS_END, 0x2000)

    def test_the_frozen_modules_are_slices_1_and_2_byte_for_byte_under_two_comment_lines(self):
        for module, digest in ((frozen, SLICE1_SHA256), (frozen2, SLICE2_SHA256)):
            first, second, body = Path(module.__file__).read_bytes().split(b'\n', 2)
            self.assertTrue(first.startswith(b'# FROZEN') and second.startswith(b'# '))
            self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
            self.assertEqual((module.MARK_OFFSET, module.MARK_SIZE), (rules.MARK_OFFSET, rules.MARK_SIZE))
        self.assertFalse(hasattr(frozen, 'MARK_SIGNATURE'))
        self.assertEqual(frozen2.MARK_SIGNATURE, b'QBMEDv2\0')
        self.assertEqual(rules.MARK_SIGNATURE, b'QBMEDv3\0')
        self.assertEqual(rules.MARK_SIZE, struct.calcsize('<8sIII'))
        self.assertEqual(rules._TEMPLATE[rules.MARK_OFFSET:rules.MARK_OFFSET + rules.MARK_SIZE], b'\xcc' * rules.MARK_SIZE)


class PositionTables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = XbeImage(retail_bytes())

    def expected(self, rate, *, halfbacks=True):
        scales, zeros, accept = [], [], []
        for position in rules.POSITION_CLASSES:
            value = 2 * position.base_chance / 1e8 * (rate / 310) / (position.zero_point - position.reference_durability)
            scales.append(0.0 if position.name == 'halfback' and not halfbacks else value * 2**31)
            zeros.append(position.zero_point)
            for group in range(6):   # one threshold per week group, read at the group's first week
                week = WEEK_GROUPS.index(group)
                probability = next(p for last, p in position.accept if week <= last)
                accept.append(round(probability * 2**31))
        n = len(rules.POSITION_CLASSES)
        return (struct.pack(f'<{n}f', *scales), struct.pack(f'<{n}I', *zeros), struct.pack(f'<{6 * n}I', *accept),
                int(rate > 0))

    def installed(self, bank):
        n = len(rules.POSITION_CLASSES)

        def read(name, size):
            return bank[rules.LABELS[name]:rules.LABELS[name] + size]
        return read('pos_scale', 4 * n), read('pos_zero', 4 * n), read('pos_accept', 24 * n), bank[rules.LABELS['pos_enabled']]

    def test_linked_bank_tables_equal_the_module_constants_for_realistic_and_custom(self):
        # Realistic, Custom 0, Custom 0.155 percent and Custom 100 percent.
        for rate in (rules.DEFAULT_RATE, 0, 155, 100_000):
            with self.subTest(rate=rate):
                bank = rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP, rate=rate)
                self.assertEqual(self.installed(bank), self.expected(rate))
                L = rules.LABELS
                self.assertEqual(bank[L['pos_slots']:L['pos_slots'] + 4 * len(SLOTS)], bytes(sum(SLOTS, ())))
                self.assertEqual(L['pos_enabled'], L['pos_slots'] + 4 * len(SLOTS))
                self.assertEqual(bank[L['pos_week_group']:L['pos_week_group'] + 32], bytes(WEEK_GROUPS))
                self.assertEqual(struct.unpack_from('<4i', bank, L['pos_year']), (-1, -1, -1, -1))
                self.assertEqual([L[name] - L['pos_year'] for name in ('pos_week', 'pos_club_a', 'pos_club_b')],
                                 [4, 8, 12])
                for name, size in (('pos_key', 4), ('pos_seq', 4), ('pos_hash', 4), ('pos_sample', 4),
                                   ('pos_wide', 8), ('pos_class', 4), ('victim_side', 4), ('victim_slot', 4),
                                   ('accept_ptr', 4), ('pos_plays', 4), ('pos_hits', 48), ('pos_commits', 48),
                                   ('pos_effective', 48)):
                    self.assertEqual(bank[L[name]:L[name] + size], bytes(size), name)
        with mock.patch.object(rules, 'HALFBACK_SUPPLEMENT', False):
            bank = rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP, rate=rules.DEFAULT_RATE)
            self.assertEqual(self.installed(bank), self.expected(rules.DEFAULT_RATE, halfbacks=False))

    def test_class_constants_keep_the_fixed_design_values_and_acceptance_rules(self):
        self.assertEqual([(p.name, p.zero_point, p.reference_durability) for p in rules.POSITION_CLASSES],
                         [('tackle', 110, 93), ('guard', 110, 91), ('center', 110, 91), ('end', 100, 81),
                          ('halfback', 100, 83), ('receiver', 100, 78), ('tight_end', 100, 80), ('fullback', 105, 85),
                          ('defensive_tackle', 100, 80), ('linebacker', 100, 79), ('cornerback', 100, 78),
                          ('safety', 100, 78)])
        self.assertEqual(rules.POSITION_CLASSES[:5], frozen2.POSITION_CLASSES)   # slice 2's rows are not touched
        self.assertEqual(rules.ACCEPT_WEEK_BOUNDARIES, (1, 2, 3, 7, 15, 31))
        self.assertEqual(rules.POSITION_WEEK_GROUPS, WEEK_GROUPS)
        self.assertIs(rules.HALFBACK_SUPPLEMENT, True)
        for position in rules.POSITION_CLASSES:
            with self.subTest(position.name):
                self.assertGreater(position.base_chance, 0)
                self.assertEqual(position.accept[-1][0], 31)
                weeks = dict(position.accept)
                self.assertEqual(max(weeks.values()), 1.0)
                self.assertAlmostEqual(weeks[1], .84 * weeks[2], delta=.0005)  # weeks 0 and 1: 0.84 x two weeks
                self.assertEqual(tuple(last for last, _ in position.accept), rules.ACCEPT_WEEK_BOUNDARIES)
                groups = rules.position_accept_thresholds(position)
                self.assertEqual(len(groups), 6)
                self.assertEqual(rules.position_accept_by_week(position), [groups[g] for g in WEEK_GROUPS])
                # Slice 2's 32-entry tables and slice 3's six groups give the same threshold for every week.
                if position.name in [p.name for p in frozen2.POSITION_CLASSES]:
                    self.assertEqual(rules.position_accept_by_week(position), frozen2.position_accept_thresholds(position))
        broken = rules.PositionClass('broken', 1, 90, 100, ((1, .5), (30, 1.0)))
        for accept in (((1, .5), (30, 1.0)), ((1, .5), (2, .5), (3, 1.0), (7, 0), (15, 0)),
                       ((1, .5), (2, .5), (3, 1.0), (6, 0), (15, 0), (31, 0)),
                       ((1, .5), (2, .5), (3, 1.5), (7, 0), (15, 0), (31, 0))):
            with self.assertRaises(ValueError):
                rules.position_accept_thresholds(broken._replace(accept=accept))

    def test_second_diagnosis_copies_are_the_games_bytes_bound_to_the_shared_routines(self):
        bank = rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP)
        rows = {row[0]: row for row in rules._LOCAL_FUNCTIONS}
        for copy, original in (('pos_descriptor', 'descriptor'), ('pos_duration', 'duration')):
            with self.subTest(copy):
                name, at, size, pin, fields = rows[copy]
                self.assertEqual(rows[original][1:], (at, size, pin, fields))
                linked = {}
                for label in (copy, original):
                    body = bytearray(bank[rules.LABELS[label]:rules.LABELS[label] + size])
                    targets = []
                    for field, relative, _, _ in fields:
                        value = struct.unpack_from('<I', body, field)[0]
                        where = BANK + rules.LABELS[label] + field
                        targets.append((value + where + 4) & 0xFFFFFFFF if relative else value)
                        body[field:field + 4] = self.image.read(at + field, 4)
                    self.assertEqual(bytes(body), self.image.read(at, size))
                    linked[label] = targets
                # Both copies call the same shared group, weeks, private generator and game routines.
                self.assertEqual(linked[copy], linked[original])
        self.assertEqual(sum(size for _, _, size, _, _ in rules._LOCAL_FUNCTIONS), 810 + 139 + 93)


class WeeklyHalfbackEdit(unittest.TestCase):
    def test_weekly_edit_is_the_running_back_owners_jump_put_back_to_the_games_tail(self):
        self.assertEqual((rules.WEEKLY_HALFBACK_SITE, rules.WEEKLY_HALFBACK_ORIGINAL),
                         (running_backs.WEEKLY_SITE, running_backs.WEEKLY_BEFORE))
        self.assertEqual(retail_weekly_tail(), rules.WEEKLY_HALFBACK_ORIGINAL)
        owner = running_backs.sites(RB)[0]
        edits = rules.edits(BANK, SIM, DATA, LINEUP, rb_va=RB)
        self.assertEqual(edits[-1], ('weekly_halfback', owner[1], owner[3], owner[2]))
        self.assertIn((rules.WEEKLY_HALFBACK_SITE, 5), rules.FIXED_SPANS)
        self.assertEqual(edits[:-1], rules.edits(BANK, SIM, DATA, LINEUP))
        for rate in (1, 155, rules.DEFAULT_RATE, 100_000):
            self.assertEqual(rules.edits(BANK, SIM, DATA, rate=rate, rb_va=RB)[-1][0], 'weekly_halfback')
        # No running-back owner, Custom 0 percent, or the halfback fallback: the site is not part of the option.
        self.assertNotIn('weekly_halfback', [edit[0] for edit in rules.edits(BANK, SIM, DATA, LINEUP)])
        self.assertNotIn('weekly_halfback', [edit[0] for edit in rules.edits(BANK, SIM, DATA, rate=0, rb_va=RB)])
        with mock.patch.object(rules, 'HALFBACK_SUPPLEMENT', False):
            self.assertNotIn('weekly_halfback', [edit[0] for edit in rules.edits(BANK, SIM, DATA, rb_va=RB)])
        for invalid in (0, -1, 1 << 32, True, 0x1519A80 + .5):
            with self.subTest(rb_va=invalid), self.assertRaises(ValueError):
                rules.edits(BANK, SIM, DATA, rb_va=invalid)


def retail_weekly_tail():
    return XbeImage(retail_bytes()).read(rules.WEEKLY_HALFBACK_SITE, 5)


if __name__ == '__main__':
    unittest.main()
