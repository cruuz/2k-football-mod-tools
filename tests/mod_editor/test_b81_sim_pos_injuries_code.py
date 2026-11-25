"""Slices 2 and 3 code module: generated template, installer tables, weekly edit and the frozen slice 1, 2 and 3 modules.

pos2/DESIGN.md and pos3/DESIGN.md section 6 test 3; the long-franchise stability piece, pos3/DESIGN.md addendum A.6
test 2. The slice 3 template facts are checked on the frozen slice 3 module (the bytes of 712835585), and the current
template against it. Native behaviour is in test_b81_sim_pos_injuries_native.py.
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
from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice3 as frozen3
from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_v4 as frozen4  # b81 game outcomes
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
# The bytes of `git show 712835585:mod_editor/core/nfl2k5_sim_qb_injuries_code.py`, the handed-over slice 3 head.
SLICE3_SHA256 = '91184562d94f80fe78feec3cc80d78d2ab5df39dc90213e55ca0419df15f232f'
V4_SHA256 = 'd0c34226fe9ed023c88ee57ec105d76d00c349e86166244b430893d7338e2284'   # b81 game outcomes: revision 4 (bb5a408b1), frozen when revision 5 added K and P
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
# Long-franchise stability (pos3/DESIGN.md addendum A.3): the only source lines added to slice 3, and the new piece.
STABILITY_LINES = {'clinical.S': ('    call STABILITY', '    fmul DWORD PTR [STAB_FACTOR+48]'),
                   'positions.S': ('    call STABILITY', '    fmul DWORD PTR [STAB_FACTOR+ecx*4]')}
STABILITY_PIECE = (0x1C00, 0x1E88)
# Template bytes that differ from the frozen slice 3 template: in the clinical piece from its first displacement or
# address that crosses the added call to its new end, in the positions piece likewise, and the stability piece.
CHANGED_FROM_SLICE3 = ((0x3F, 0x13B8), (0x1402, 0x1B01), STABILITY_PIECE)
INSERTED = {'clinical': 0x119, 'positions': 0x14C7}   # where `call STABILITY` now starts in each piece


def _strip_stability(folder):
    """Remove the four stability lines (each exactly once) from copied sources."""
    for name, lines in STABILITY_LINES.items():
        text = (folder / name).read_text().split('\n')
        for line in lines:
            found = [n for n, each in enumerate(text) if each.split('#')[0].rstrip() == line]
            assert len(found) == 1, (name, line, found)
            del text[found[0]]
        (folder / name).write_text('\n'.join(text))


def _without_stability(build):
    build.PIECES = tuple(piece for piece in build.PIECES if piece[0] != 'stability')
    for name in ('STABILITY', 'STAB_FACTOR'):
        del build.LOCAL[name]
    del build.EXPORTED['stability']


# b81 game outcomes, revision 5: every positions.S change it made (current lines -> revision 4 lines; a tuple is a run
# of consecutive lines, matched exactly once; an empty replacement deletes it).
KICKER_PUNTER_EDITS = (
    (('.set SLOT_COUNT, 29', '.set CLASS_COUNT, 14',
      '.set STAB_CLASSES, 12                  # classes with a long-franchise factor; kicker and punter (12, 13) take none'),
     ('.set SLOT_COUNT, 27', '.set CLASS_COUNT, 12')),
    (('    cmp ecx, STAB_CLASSES',
      '    jae no_factor                       # b81 game outcomes: the kicker and punter classes have no stability factor',
      '    fmul DWORD PTR [STAB_FACTOR+ecx*4]  # the class\'s factor, exactly 1.0 in seasons one and two',
      'no_factor:'),
     ('    fmul DWORD PTR [STAB_FACTOR+ecx*4]  # the class\'s factor, exactly 1.0 in seasons one and two',)),
    (('    and eax, 3                          # rule: 0 every scrimmage play, 1 rushing ball carrier, 2 rush play, 3 specialists',
      '    jz exposed',
      '    cmp eax, 3',
      '    je specialists'),
     ('    and eax, 3                          # rule: 0 every scrimmage play, 1 rushing ball carrier, 2 rush play',
      '    jz exposed')),
    (('    jne next',
      '    jmp exposed',
      'specialists:',
      '    # rule 3 (b81 game outcomes, coordinator R3 ruling): the kicker and punter rows count only while both specialist',
      '    # slots of that side hold their own specialists (stored position 1 in slot 32, 2 in slot 14). While either is out,',
      '    # the other covers both jobs unexposed, so a club never loses both and puts a position player in to kick or punt.',
      '    mov eax, [ecx+32*4+8]', '    test eax, eax', '    jz next', '    cmp BYTE PTR [eax+0x35], 1', '    jne next',
      '    mov eax, [ecx+14*4+8]', '    test eax, eax', '    jz next', '    cmp BYTE PTR [eax+0x35], 2', '    jne next',
      'exposed:'),
     ('    jne next', 'exposed:')),
    (('pos_hits: .zero 4*CLASS_COUNT',), ('pos_hits: .zero 48',)),
    (('pos_commits: .zero 4*CLASS_COUNT',), ('pos_commits: .zero 48',)),
    (('pos_effective: .zero 4*CLASS_COUNT',), ('pos_effective: .zero 48',)),
    (('pos_scale: .zero 4*CLASS_COUNT          # CLASS_COUNT floats, installer',),
     ('pos_scale: .zero 48                     # CLASS_COUNT floats, installer',)),
    (('pos_zero: .zero 4*CLASS_COUNT           # CLASS_COUNT dwords, installer: the zero point K per class',),
     ('pos_zero: .zero 48                      # CLASS_COUNT dwords, installer: the zero point K per class',)),
    (('pos_accept: .zero 24*CLASS_COUNT        # CLASS_COUNT tables of six thresholds by week group, installer',),
     ('pos_accept: .zero 288                   # CLASS_COUNT tables of six thresholds by week group, installer',)),
    (('    # b81 game outcomes (coordinator R2/R3): the kicker (lineup slot 32) and the punter (slot 14) of the offense, on every',
      '    # scrimmage play of their offense while both slots hold their own specialists (rule 3), LAST in the walk so every',
      '    # earlier entry\'s hit decision is unchanged.',
      '    .byte 12, 0, 32, 3',
      '    .byte 13, 0, 14, 3'), ()),
)


def _revert_kicker_punter(folder):
    """Turn copied revision 5 sources back into revision 4's (each changed run of lines exactly once)."""
    text = (folder / 'positions.S').read_text().split('\n')
    for current, original in KICKER_PUNTER_EDITS:
        found = [n for n in range(len(text) - len(current) + 1)
                 if [line.rstrip() for line in text[n:n + len(current)]] == list(current)]
        assert len(found) == 1, (current[0], found)
        text[found[0]:found[0] + len(current)] = list(original)
    (folder / 'positions.S').write_text('\n'.join(text))
# pos2/DESIGN.md section 2 and pos3/DESIGN.md section 1: class, side (0 offense, 1 defense), lineup slot, flags
# (bits 0-1 the rule: 0 every scrimmage play, 1 rushing ball carrier, 2 rush play; bits 4-7 the weight in sixteenths).
SLOTS = ((0, 0, 12, 0), (0, 0, 13, 0), (1, 0, 10, 0), (1, 0, 11, 0), (2, 0, 9, 0), (3, 1, 15, 0), (3, 1, 16, 0),
         (4, 0, 1, 1), (4, 0, 3, 1),
         (5, 0, 4, 0), (5, 0, 5, 0), (5, 0, 6, 0), (5, 0, 7, 0x40), (6, 0, 8, 0), (7, 0, 2, 0x02), (8, 1, 17, 0),
         (8, 1, 18, 0), (9, 1, 19, 0), (9, 1, 20, 0), (9, 1, 21, 0), (9, 1, 22, 0x40), (10, 1, 24, 0),
         (10, 1, 25, 0), (10, 1, 26, 0), (11, 1, 23, 0), (11, 1, 27, 0), (11, 1, 28, 0x40))
# b81 game outcomes, revision 5: the offense's kicker (slot 32) and punter (slot 14), every scrimmage play, walked last.
KICKER_PUNTER_SLOTS = ((12, 0, 32, 3), (13, 0, 14, 3))   # rule 3: while both specialists play
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
                if source.suffix in ('.S', '.c') and source.name not in ('positions.S', 'stability.S'):
                    shutil.copy(source, folder / source.name)
            shutil.copy(TOOLS / 'positions.S', folder / 'positions.S')
            _strip_stability(folder)
            (folder / 'positions.S').unlink()
            for name, line in ADDED_LINES.items():
                lines = (folder / name).read_text().split('\n')
                found = [n for n, text in enumerate(lines) if text.split('#')[0].rstrip() == line]
                self.assertEqual(len(found), 1, name)
                del lines[found[0]]
                (folder / name).write_text('\n'.join(lines))
            build.HERE = folder
            _without_stability(build)
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
        old, new = frozen._TEMPLATE, frozen3._TEMPLATE
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
        self.assertEqual(frozen3.LABELS['finished'], frozen.LABELS['finished'])
        linked = frozen3._link_authored(BANK, SIM, DATA, LINEUP + 0x455)
        self.assertEqual(linked[FINISHED:FINISHED + 5], b'\xe8' + struct.pack('<i', 0x1400 - FINISHED - 5))
        # The positions piece ends before the recovery piece at 0x2000, followed only by fill.
        self.assertEqual(frozen3.LABELS['positions'], 0x1400)
        self.assertEqual(new[POSITIONS_END:0x2000], b'\xcc' * (0x2000 - POSITIONS_END))
        self.assertEqual(old[0x13A8:0x2000], b'\xcc' * (0x2000 - 0x13A8))
        unmoved = {name for name, at in frozen.LABELS.items() if at < FINISHED or 0x2000 <= at < 0x3100
                   or 0x3200 <= at < 0x3600 or at >= 0x3840}
        self.assertEqual({name: frozen3.LABELS[name] for name in unmoved}, {name: frozen.LABELS[name] for name in unmoved})
        self.assertEqual(set(frozen.LABELS) - set(frozen3.LABELS), set())

    def test_template_equals_the_frozen_slice_2_template_outside_the_positions_piece(self):
        old, new = frozen2._TEMPLATE, frozen3._TEMPLATE
        differ = [n for n in range(len(new)) if old[n] != new[n]]
        self.assertEqual((differ[0], differ[-1] + 1), CHANGED_FROM_SLICE2)
        self.assertEqual({name: at for name, at in frozen3.LABELS.items() if not 0x1400 <= at < 0x2000},
                         {name: at for name, at in frozen2.LABELS.items() if not 0x1400 <= at < 0x2000})
        self.assertEqual(set(frozen3.LABELS) - set(frozen2.LABELS), {'pos_week_group'})
        # Outside the piece, relocations are slice 2's; the only target that moved is pos_year, which context.S and
        # fixture_start.S clear on a re-entered fixture (its value is the label's bank offset).
        moved = {('bank', frozen2.LABELS['pos_year']): ('bank', frozen3.LABELS['pos_year'])}
        self.assertEqual([r for r in frozen3._RELOCATIONS if not 0x1400 <= r[0] < 0x2000],
                         [r[:2] + moved.get(r[2:], r[2:]) for r in frozen2._RELOCATIONS if not 0x1400 <= r[0] < 0x2000])
        self.assertEqual(sum(r[2:] in moved for r in frozen2._RELOCATIONS if not 0x1400 <= r[0] < 0x2000), 2)
        self.assertEqual(frozen3._LOCAL_FUNCTIONS, frozen2._LOCAL_FUNCTIONS)
        end = 0x2000
        while new[end - 1] == 0xCC:
            end -= 1
        self.assertEqual(end, POSITIONS_END)
        self.assertLess(POSITIONS_END, 0x2000)

    def test_the_frozen_modules_are_slices_1_2_and_3_byte_for_byte_under_two_comment_lines(self):
        for module, digest in ((frozen, SLICE1_SHA256), (frozen2, SLICE2_SHA256), (frozen3, SLICE3_SHA256),
                               (frozen4, V4_SHA256)):
            first, second, body = Path(module.__file__).read_bytes().split(b'\n', 2)
            self.assertTrue(first.startswith(b'# FROZEN') and second.startswith(b'# '))
            self.assertEqual(hashlib.sha256(body).hexdigest(), digest)
            self.assertEqual((module.MARK_OFFSET, module.MARK_SIZE), (frozen3.MARK_OFFSET, frozen3.MARK_SIZE))
        self.assertFalse(hasattr(frozen, 'MARK_SIGNATURE'))
        self.assertEqual(frozen2.MARK_SIGNATURE, b'QBMEDv2\0')
        self.assertEqual(frozen3.MARK_SIGNATURE, b'QBMEDv3\0')
        self.assertEqual(frozen4.MARK_SIGNATURE, b'QBMEDv4\0')
        self.assertEqual(rules.MARK_SIGNATURE, b'QBMEDv5\0')   # b81 game outcomes: + kicker and punter classes
        self.assertEqual((rules.MARK_OFFSET, rules.MARK_SIZE), (frozen3.MARK_OFFSET, frozen3.MARK_SIZE))
        self.assertEqual(rules._TEMPLATE[rules.MARK_OFFSET:rules.MARK_OFFSET + rules.MARK_SIZE], b'\xcc' * rules.MARK_SIZE)
        self.assertEqual(frozen3.MARK_SIZE, struct.calcsize('<8sIII'))
        self.assertEqual(frozen3._TEMPLATE[frozen3.MARK_OFFSET:frozen3.MARK_OFFSET + frozen3.MARK_SIZE], b'\xcc' * frozen3.MARK_SIZE)


class StabilityTemplate(unittest.TestCase):
    """pos3/DESIGN.md addendum A.6 test 2: build.py --check, and the template equals the frozen slice 3 template outside
    the stability piece and the two edits in each of the clinical and positions pieces (and what follows them).
    Since revision 5 (b81 game outcomes) these are facts of the frozen revision 4 module; KickerPunterTemplate below
    relates revision 5 to it."""

    def test_build_check_passes_and_slice_3_sources_changed_only_by_the_four_lines_and_the_piece(self):
        _toolchain()
        subprocess.run([sys.executable, str(TOOLS / 'build.py'), '--check'], check=True)
        build = _build_module()
        self.assertEqual([piece for piece in build.PIECES if piece[0] in ('positions', 'stability', 'recovery')],
                         [('positions', 0x1400), ('stability', 0x1C00), ('recovery', 0x2000)])
        self.assertEqual((build.LOCAL['STABILITY'], build.LOCAL['STAB_FACTOR']),
                         ('stability.stability', 'stability.stab_factor'))
        with tempfile.TemporaryDirectory(prefix='2k5-slice3-') as folder:
            folder = Path(folder)
            for source in TOOLS.iterdir():
                if source.suffix in ('.S', '.c') and source.name != 'stability.S':
                    shutil.copy(source, folder / source.name)
            _revert_kicker_punter(folder)
            _strip_stability(folder)
            build.HERE = folder
            _without_stability(build)
            generated = build.render()
        text = Path(frozen3.__file__).read_text(encoding='utf-8')
        self.assertEqual(text[text.index(build.DIVIDER):], generated)

    def test_template_equals_the_frozen_slice_3_template_outside_the_stated_ranges(self):
        rules = frozen4                                  # revision 4's template (frozen since revision 5)
        old, new = frozen3._TEMPLATE, rules._TEMPLATE
        self.assertEqual((len(old), len(new)), (rules.CODE_SIZE, rules.CODE_SIZE))
        differ = [n for n in range(len(new)) if old[n] != new[n]]
        for start, end in CHANGED_FROM_SLICE3:
            here = [n for n in differ if start <= n < end]
            self.assertEqual((here[0], here[-1] + 1), (start, end), hex(start))
        self.assertEqual([hex(n) for n in differ if not any(a <= n < b for a, b in CHANGED_FROM_SLICE3)], [])
        # Each piece ends before the next: clinical before 0x1400, positions before 0x1C00, stability before 0x2000.
        for start, end, limit in ((0, 0x13B8, 0x1400), (0x1400, 0x1B01, 0x1C00), (0x1C00, 0x1E88, 0x2000)):
            self.assertEqual(new[end:limit], b'\xcc' * (limit - end), hex(start))
            self.assertNotEqual(new[end - 1], 0xCC)
        self.assertEqual(rules.LABELS['stability'], STABILITY_PIECE[0])
        # Before the added call in each piece only displacement and address fields change: jumps and calls that cross
        # it, and the relocated addresses of labels after it.
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        except ImportError:
            self.skipTest('capstone is required to decode the slice 3 instructions')
        relocated = {offset for offset, *_ in frozen3._RELOCATIONS}
        for piece, start in (('clinical', 0), ('positions', 0x1400)):
            end = INSERTED[piece]
            fields = set(relocated)
            for instruction in Cs(CS_ARCH_X86, CS_MODE_32).disasm(old[start:end], start):
                if instruction.mnemonic == 'call' or instruction.mnemonic.startswith('j'):
                    width = 1 if instruction.size == 2 else 4
                    fields.add(instruction.address + instruction.size - width)
                    if width == 1:
                        relocated.add(instruction.address + 1)
            for n in differ:
                if start <= n < end:
                    self.assertTrue(any(field <= n < field + 4 for field in fields) or n in relocated, hex(n))
            self.assertIn((end + 1, True, 'bank', STABILITY_PIECE[0] - 4), rules._RELOCATIONS)   # call STABILITY
        # Relocations outside the three ranges are slice 3's, only with the moved labels' new offsets.
        moved = {('bank', frozen3.LABELS[name]): ('bank', rules.LABELS[name]) for name in frozen3.LABELS}
        outside = lambda rows: [row for row in rows if not any(a <= row[0] < b for a, b in CHANGED_FROM_SLICE3)]
        self.assertEqual([row[:2] for row in outside(rules._RELOCATIONS)], [row[:2] for row in outside(frozen3._RELOCATIONS)])
        self.assertEqual(rules._LOCAL_FUNCTIONS, frozen3._LOCAL_FUNCTIONS)
        self.assertEqual(set(rules.LABELS) - set(frozen3.LABELS),
                         {'stability', 'stab_factor', 'stab_reference', 'stab_year', 'stab_zero', 'stab_mode',
                          'stab_class', 'stab_starters', 'stab_sum', 'stab_count'})
        self.assertEqual(set(frozen3.LABELS) - set(rules.LABELS), set())
        unmoved = {name for name, at in frozen3.LABELS.items() if at < INSERTED['clinical'] or 0x2000 <= at}
        self.assertEqual({name: rules.LABELS[name] for name in unmoved}, {name: frozen3.LABELS[name] for name in unmoved})

    def test_the_four_lines_link_to_the_piece_and_its_factor_table(self):
        for module in (frozen4, rules):                  # revision 4 and revision 5 (the same four lines)
            with self.subTest(revision=module.MARK_SIGNATURE):
                self._four_lines(module)

    def _four_lines(self, rules):
        linked = rules._link_authored(BANK, SIM, DATA, LINEUP + 0x455)
        L = rules.LABELS
        factor = BANK + L['stab_factor']
        for at in INSERTED.values():
            self.assertEqual(linked[at:at + 5], b'\xe8' + struct.pack('<i', L['stability'] - at - 5))
        clinical = bytes(linked[:0x1400])
        # evaluate_gate: fld [table]; fmul [slider]; fmul [stab_factor+48]; fild [gate sample]
        self.assertEqual(clinical.count(b'\xd8\x0d' + struct.pack('<I', 0xE60204) + b'\xd8\x0d' + struct.pack('<I', factor + 48)
                                        + b'\xdb\x05' + struct.pack('<I', BANK + L['private_rng'] - 20)), 1)
        # effective: fld [pos_scale+ecx*4]; fmul [slider]; fmul [stab_factor+ecx*4]; fistp qword [pos_wide]. Revision 5
        # (b81 game outcomes) skips the factor for classes 12 and 13 (kicker, punter): cmp ecx, 12; jae over the fmul.
        skip = b'\x83\xf9\x0c\x73\x07' if rules.MARK_SIGNATURE == b'QBMEDv5\0' else b''
        positions = bytes(linked[0x1400:0x1C00])
        self.assertEqual(positions.count(b'\xd8\x0d' + struct.pack('<I', 0xE60204) + skip + b'\xd8\x0c\x8d'
                                         + struct.pack('<I', factor) + b'\xdf\x3d' + struct.pack('<I', BANK + L['pos_wide'])), 1)
        self.assertEqual(L['stab_count'], L['stab_sum'] + 52)            # one loop clears both
        self.assertEqual(L['stab_factor'] % 4, 0)


class KickerPunterTemplate(unittest.TestCase):
    """b81 game outcomes, revision 5: the current sources less exactly the kicker and punter edits regenerate the frozen
    revision 4 module byte for byte, and the template differs from revision 4's only inside the positions piece."""

    def test_current_sources_without_the_kicker_punter_edits_regenerate_revision_4(self):
        _toolchain()
        build = _build_module()
        with tempfile.TemporaryDirectory(prefix='2k5-v4-') as folder:
            folder = Path(folder)
            for source in TOOLS.iterdir():
                if source.suffix in ('.S', '.c'):
                    shutil.copy(source, folder / source.name)
            _revert_kicker_punter(folder)
            build.HERE = folder
            generated = build.render()
        text = Path(frozen4.__file__).read_text(encoding='utf-8')
        self.assertEqual(text[text.index(build.DIVIDER):], generated)

    def test_template_differs_from_revision_4_only_inside_the_positions_piece(self):
        old, new = frozen4._TEMPLATE, rules._TEMPLATE
        self.assertEqual((len(old), len(new)), (rules.CODE_SIZE, rules.CODE_SIZE))
        differ = [n for n in range(len(new)) if old[n] != new[n]]
        self.assertEqual(hex(differ[0]), '0x1402')
        end = max(n for n in range(0x1400, 0x1C00) if new[n] != 0xCC) + 1
        self.assertLessEqual(differ[-1] + 1, end)
        self.assertEqual(new[end:0x1C00], b'\xcc' * (0x1C00 - end))      # still ends before the stability piece
        self.assertEqual(set(rules.LABELS), set(frozen4.LABELS))
        moved = {name for name in rules.LABELS if rules.LABELS[name] != frozen4.LABELS[name]}
        self.assertTrue(all(0x1400 <= frozen4.LABELS[name] < 0x1C00 and 0x1400 <= rules.LABELS[name] < 0x1C00
                            for name in moved), moved)
        # Relocations outside the piece are revision 4's, only with the moved labels' new offsets.
        new_offset = {frozen4.LABELS[name]: rules.LABELS[name] for name in moved}
        outside = lambda rows: [row for row in rows if not 0x1400 <= row[0] < 0x1C00]
        self.assertEqual(outside(rules._RELOCATIONS),
                         [(at, relative, family, new_offset.get(addend, addend) if family == 'bank' else addend)
                          for at, relative, family, addend in outside(frozen4._RELOCATIONS)])
        self.assertEqual(rules._LOCAL_FUNCTIONS, frozen4._LOCAL_FUNCTIONS)
        self.assertEqual(rules.LABELS['pos_slots'] + 4 * 29, rules.LABELS['pos_enabled'])   # 29 rows of four bytes
        self.assertEqual(bytes(new[rules.LABELS['pos_slots'] + 4 * 27:rules.LABELS['pos_slots'] + 4 * 29]),
                         bytes((12, 0, 32, 3, 13, 0, 14, 3)))   # rule 3: only while both specialists play


class StabilityTables(unittest.TestCase):
    """pos3/DESIGN.md addendum A.2, A.4 and A.6: the installed stability tables for each mode."""

    @classmethod
    def setUpClass(cls):
        cls.image = XbeImage(retail_bytes())

    def read(self, bank):
        L = rules.LABELS
        return {'factor': struct.unpack_from('<13I', bank, L['stab_factor']),
                'reference': struct.unpack_from('<13f', bank, L['stab_reference']),
                'year': struct.unpack_from('<10f', bank, L['stab_year']),
                'zero': bytes(bank[L['stab_zero']:L['stab_zero'] + 13]),
                'class': bytes(bank[L['stab_class']:L['stab_class'] + 17]),
                'starters': bytes(bank[L['stab_starters']:L['stab_starters'] + 17]),
                'mode': bank[L['stab_mode']], 'sums': bytes(bank[L['stab_sum']:L['stab_count'] + 52])}

    def test_constants_are_the_measured_references_and_the_designs_rule(self):
        self.assertEqual(rules.STABILITY_REFERENCE, (17.627, 18.847, 18.803, 19.526, 17.703, 22.138, 20.803, 21.261,
                                                     20.343, 20.551, 23.144, 21.840, 25.807))   # order S0, 64001-64004
        # Revision 5 (b81 game outcomes): the kicker and punter classes take no factor; the thirteen stay these.
        self.assertEqual(rules.STABILITY_POSITION_CLASSES, rules.POSITION_CLASSES[:12])
        self.assertEqual(tuple(p.name for p in rules.POSITION_CLASSES[12:]), ('kicker', 'punter'))
        self.assertEqual(rules.STABILITY_CLASS_NAMES, tuple(p.name for p in rules.STABILITY_POSITION_CLASSES) + ('quarterback',))
        self.assertEqual(rules.STABILITY_CLASS_NAMES, frozen4.STABILITY_CLASS_NAMES)
        self.assertEqual((rules.STABILITY_MODE, rules.STABILITY_CLASSES_OFF, rules.STABILITY_YEAR_SLOPE),
                         ('adaptive', (), .055))
        self.assertEqual(rules.STABILITY_MODES, {'off': 0, 'year': 1, 'adaptive': 2})
        self.assertEqual([round(value, 3) for value in rules.stability_year_factors()],
                         [1.0, 1.0, .924, .879, .839, .839, .839, .839, .839, .839])
        template = self.read(rules._TEMPLATE)
        self.assertEqual(template['factor'], (0x3F800000,) * 13)
        self.assertEqual(template['sums'], bytes(104))
        self.assertEqual(template['mode'], 0)
        # By stored position QB K P WR CB FS SS HB FB TE OLB ILB C G T DT DE (pos3/DESIGN.md addendum A.2).
        self.assertEqual(template['class'], bytes((12, 255, 255, 5, 10, 11, 11, 4, 7, 6, 9, 9, 2, 1, 0, 8, 3)))
        self.assertEqual(template['starters'], bytes((1, 0, 0, 3, 3, 1, 1, 2, 1, 1, 3, 3, 1, 2, 2, 2, 2)))

    def test_tables_for_each_mode_rate_and_switched_off_class(self):
        zero = bytes((110, 110, 110, 100, 100, 100, 100, 105, 100, 100, 100, 100, 100))
        default_class = bytes((12, 255, 255, 5, 10, 11, 11, 4, 7, 6, 9, 9, 2, 1, 0, 8, 3))
        year = struct.unpack('<10f', struct.pack('<10f', 1, 1, 1 / 1.0825, 1 / 1.1375, *([1 / 1.1925] * 6)))
        for mode, value in (('adaptive', 2), ('year', 1), ('off', 0)):
            for rate in (rules.DEFAULT_RATE, 0, 155, 100_000):
                with self.subTest(mode=mode, rate=rate), mock.patch.object(rules, 'STABILITY_MODE', mode):
                    bank = rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP, rate=rate)
                    tables = self.read(bank)
                    self.assertEqual(tables['mode'], value if rate else 0)
                    self.assertEqual(tables['reference'], struct.unpack('<13f', struct.pack('<13f', *rules.STABILITY_REFERENCE)))
                    self.assertEqual(tables['zero'], zero)
                    for got, expected in zip(tables['year'], year):
                        self.assertAlmostEqual(got, expected, places=6)
                    self.assertEqual(tables['year'], struct.unpack('<10f', struct.pack('<10f', *rules.stability_year_factors())))
                    self.assertEqual(tables['class'], default_class)
                    self.assertEqual(tables['factor'], (0x3F800000,) * 13)
        positions = {name: [n for n, index in enumerate(default_class) if index == rules.STABILITY_CLASS_NAMES.index(name)]
                     for name in rules.STABILITY_CLASS_NAMES}
        self.assertEqual(positions['linebacker'], [10, 11])
        self.assertEqual(positions['safety'], [5, 6])
        self.assertEqual(positions['quarterback'], [0])
        for name in rules.STABILITY_CLASS_NAMES:
            with self.subTest(off=name), mock.patch.object(rules, 'STABILITY_CLASSES_OFF', (name,)):
                tables = self.read(rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP))
                expected = bytearray(default_class)
                for position in positions[name]:
                    expected[position] = 0xFF
                self.assertEqual(tables['class'], bytes(expected))
                self.assertEqual(tables['mode'], 2)
        bank = bytearray(rules._TEMPLATE)
        for bad in (dict(mode='weekly'), dict(reference=(20.0,) * 12), dict(reference=(20.0,) * 12 + (0,)),
                    dict(reference=(20.0,) * 12 + (float('nan'),)), dict(reference=(20.0,) * 12 + (-1.0,)),
                    dict(classes_off=('kicker',)), dict(slope=1.0), dict(slope=-.01)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                rules._configure_stability(bank, rules.DEFAULT_RATE, **bad)


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
                walk = SLOTS + KICKER_PUNTER_SLOTS
                self.assertEqual(bank[L['pos_slots']:L['pos_slots'] + 4 * len(walk)], bytes(sum(walk, ())))
                self.assertEqual(L['pos_enabled'], L['pos_slots'] + 4 * len(walk))
                self.assertEqual(bank[L['pos_week_group']:L['pos_week_group'] + 32], bytes(WEEK_GROUPS))
                self.assertEqual(struct.unpack_from('<4i', bank, L['pos_year']), (-1, -1, -1, -1))
                self.assertEqual([L[name] - L['pos_year'] for name in ('pos_week', 'pos_club_a', 'pos_club_b')],
                                 [4, 8, 12])
                for name, size in (('pos_key', 4), ('pos_seq', 4), ('pos_hash', 4), ('pos_sample', 4),
                                   ('pos_wide', 8), ('pos_class', 4), ('victim_side', 4), ('victim_slot', 4),
                                   ('accept_ptr', 4), ('pos_plays', 4), ('pos_hits', 56), ('pos_commits', 56),
                                   ('pos_effective', 56)):   # 14 classes since revision 5
                    self.assertEqual(bank[L[name]:L[name] + size], bytes(size), name)
        with mock.patch.object(rules, 'HALFBACK_SUPPLEMENT', False):
            bank = rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP, rate=rules.DEFAULT_RATE)
            self.assertEqual(self.installed(bank), self.expected(rules.DEFAULT_RATE, halfbacks=False))

    def test_class_constants_keep_the_fixed_design_values_and_acceptance_rules(self):
        self.assertEqual([(p.name, p.zero_point, p.reference_durability) for p in rules.POSITION_CLASSES],
                         [('tackle', 110, 93), ('guard', 110, 91), ('center', 110, 91), ('end', 100, 81),
                          ('halfback', 100, 83), ('receiver', 100, 78), ('tight_end', 100, 80), ('fullback', 105, 85),
                          ('defensive_tackle', 100, 80), ('linebacker', 100, 79), ('cornerback', 100, 78),
                          ('safety', 100, 78), ('kicker', 100, 85), ('punter', 100, 88)])
        self.assertEqual(rules.POSITION_CLASSES[:5], frozen2.POSITION_CLASSES)   # slice 2's rows are not touched
        self.assertEqual(rules.POSITION_CLASSES[:12], frozen4.POSITION_CLASSES)  # revision 4's rows are not touched
        # Revision 5: kicker and punter onsets start at the slices' 0.8 targets (coordinator R2: 1.22 and 0.53 per 100
        # starter-games), the starters' base-roster Durability as reference, and the tight end's acceptance by week.
        tight_end = rules.POSITION_CLASSES[6]
        self.assertEqual([(p.base_chance, p.accept) for p in rules.POSITION_CLASSES[12:]],
                         [(229_000, tight_end.accept), (99_000, tight_end.accept)])
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
