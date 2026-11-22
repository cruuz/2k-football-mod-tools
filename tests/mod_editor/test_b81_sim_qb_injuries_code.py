"""Authored native guards, actual ELF relocation and local-game equivalence for the scheduled quarterback option."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

from mod_editor.core import nfl2k5_sim_qb_injuries_code as rules
from mod_editor.core import nfl2k5_sim_realism as simulator
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes


BANK, SIM, DATA, LINEUP = 0x1520000, 0x150E000, 0x14FD650, 0x151CE00
RB = 0x1519A80  # an installed running-back weekly entry (slice 2 parks its jump at the weekly tick)


class LinkedRules(unittest.TestCase):
    def test_external_writes_cover_the_eight_game_calls_and_only_the_completion_converter(self):
        edits = rules.edits(BANK, SIM, DATA, LINEUP)
        absolute = tuple((at, len(old)) for _, at, old, _ in edits if at < SIM)
        # Slice 2: the ninth fixed span is the weekly halfback tail, written only when the running-back owner is there.
        self.assertEqual(absolute, tuple(span for span in rules.FIXED_SPANS if span[0] != rules.WEEKLY_HALFBACK_SITE))
        self.assertEqual(len(absolute), 8)
        self.assertEqual(len(edits), 14)
        self.assertEqual(len(rules.edits(BANK, SIM, DATA)), 13)
        with_rb = rules.edits(BANK, SIM, DATA, LINEUP, rb_va=RB)
        self.assertEqual(tuple((at, len(old)) for _, at, old, _ in with_rb if at < SIM), rules.FIXED_SPANS)
        self.assertEqual(len(rules.FIXED_SPANS), 9)
        self.assertEqual(with_rb, edits + (with_rb[-1],))
        zero = rules.edits(BANK, SIM, DATA, LINEUP, rate=0)
        self.assertEqual(zero, rules.edits(BANK, SIM, DATA, rate=0))
        self.assertEqual(zero, rules.edits(BANK, SIM, DATA, LINEUP, rate=0, rb_va=RB))
        self.assertEqual(zero, tuple(edit for edit in edits if edit[0] != 'recovery'))
        by_name = {name: (at, old, new) for name, at, old, new in edits}
        self.assertEqual(by_name['completed_pass'][0], 0x1094E4)
        self.assertTrue({at for at, _ in simulator.PASS_SITES if at != 0x1094E4}.isdisjoint(dict(absolute)))
        inside = set()
        for _, at, old, new in edits:
            self.assertEqual(len(old), len(new))
            inside.update(range(at, at + len(new)))
        for start, size in ((SIM + simulator.label_offsets()['pass_scale'], 64),
                            (SIM + simulator.PASS_SCALE_OFF, 4), (SIM + simulator.RZ_PASS_SCALE_OFF, 4)):
            self.assertTrue(inside.isdisjoint(range(start, start + size)))
        for rate in (-1, 100_001, True, 3.1):
            with self.subTest(rate=rate), self.assertRaises(ValueError):
                rules.edits(BANK, SIM, DATA, LINEUP, rate=rate)

    def test_durability_exposure_duration_and_completed_accuracy_tables(self):
        template = bytearray(rules.CODE_SIZE)
        for rate in (0, 310, 100_000):
            rules._configure_tables(template, rate)
            for name, mult in (('ordinary_thresholds', 1), ('special_thresholds', 4)):
                start = rules.LABELS[name]
                actual = template[start:start + 1024]
                chance = rate / 100_000 * rules.QB_CHANCE_SCALE   # combined lever 2, frozen 1.06 (QB tables only)
                expected = [2 * chance * mult * max(0, 100 - d) / (100 - 74.72222222222223) * 2**31
                            for d in range(256)]
                self.assertEqual(actual, struct.pack('<256f', *expected))
            actual = struct.unpack_from('<256I', template, rules.LABELS['length_thresholds'])
            expected = []
            for last, value in rules.LENGTH_ACCEPT:
                expected.extend([value] * (last + 1 - len(expected)))
            self.assertEqual(actual, tuple(expected))
        actual = struct.unpack_from('<101f', template, rules.GAIN_TABLE)
        self.assertEqual(hashlib.sha256(struct.pack('<101f', *actual)).hexdigest(),
                         '4a754e8b2976bb3b82bd396869b146ef956442b6787d31237f4431032d461372')
        self.assertEqual(len(set(actual[:93])), 1)
        self.assertEqual(len(set(actual[98:])), 1)
        self.assertTrue(all(actual[n] < actual[n + 1] for n in range(92, 98)))

    def test_the_template_contains_empty_holes_for_all_four_local_game_functions(self):
        self.assertEqual(len(rules._TEMPLATE), 16_384)
        slice1 = rules._LOCAL_FUNCTIONS[:4]
        self.assertEqual([name for name, *_ in slice1], ['descriptor', 'duration', 'group', 'weeks'])
        self.assertEqual(sum(size for _, _, size, _, _ in slice1), 810)
        # Slice 2 links second copies of the first two, with the same pins and fields.
        self.assertEqual(rules._LOCAL_FUNCTIONS[4:], tuple(('pos_' + row[0],) + row[1:] for row in slice1[:2]))
        for name, _, size, _, _ in rules._LOCAL_FUNCTIONS:
            offset = rules.LABELS[name]
            self.assertEqual(rules._TEMPLATE[offset:offset + size], bytes(size), name)
        self.assertEqual(rules._TEMPLATE[rules.MARK_OFFSET:rules.MARK_OFFSET + rules.MARK_SIZE], b'\xcc' * rules.MARK_SIZE)

    def test_authored_template_rebuilds_with_its_development_toolchain(self):
        if not all(shutil.which(tool) for tool in ('gcc', 'as', 'ld')) or not importlib.util.find_spec('elftools'):
            self.skipTest('development build needs GNU i386 gcc/binutils and pyelftools')
        version = subprocess.run(['gcc', '-dumpfullversion'], capture_output=True, text=True)
        assembler = subprocess.run(['as', '--version'], capture_output=True, text=True)
        if version.stdout.strip() != '13.3.0' or '2.42' not in assembler.stdout.partition('\n')[0]:
            self.skipTest('the checked-in i386 template was generated with GCC 13.3 and GNU binutils 2.42')
        tool = Path(__file__).resolve().parents[2] / 'tools/qb_sim_injuries/build.py'
        subprocess.run([sys.executable, str(tool), '--check'], check=True)


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the native branch witnesses')
class NativeFixture(unittest.TestCase):
    """Execute the actual authored instructions on public synthetic state. Native service entry PCs are the stop points."""
    ROOT, STACK = 0x2100000, 0x3001000

    def setUp(self):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, x86_const

        self.x = x86_const
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        for start, size in ((BANK, rules.CODE_SIZE), (SIM, 0x1000), (DATA & ~0xFFF, 0x1000),
                            (self.ROOT, 0x10000), (self.STACK - 0x1000, 0x2000), (0xB72000, 0x1000), (0xA97000, 0x1000),
                            (0xE57000, 0x1000), (0xE5F000, 0x2000), (0x10B000, 0x1000),
                            (0x102000, 0x1000), (0x6C000, 0x1000), (0x3003000, 0x1000)):
            self.uc.mem_map(start, size)
        bank = rules._link_authored(BANK, SIM, DATA, LINEUP + 0x455)
        rules._configure_tables(bank, 310)
        self.uc.mem_write(BANK, bytes(bank))
        self.regs = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP', 'EFLAGS')
        self.registers = tuple(getattr(self.x, 'UC_X86_REG_' + word) for word in self.regs)
        self.teams = self.ROOT + 0x1000
        for at, value in ((0xB72918, self.ROOT), (self.ROOT + 28, self.teams), (0xE576A0, 2), (0xE5FF80, 4),
                          (0xE576A4, 8), (0xE576B8, 22), (0xE576B4, 7)):
            self.write(at, value)

    def write(self, at, value):
        self.uc.mem_write(at, struct.pack('<I', value))

    def word(self, at):
        return int.from_bytes(self.uc.mem_read(at, 4), 'little')

    def run_code(self, label, end, values):
        for register, value in zip(self.registers, values, strict=True):
            self.uc.reg_write(register, value)
        self.uc.emu_start(BANK + rules.LABELS[label], end, count=12_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), end)
        return tuple(self.uc.reg_read(r) for r in self.registers)


class NativeBranches(NativeFixture):
    def test_scheduled_and_whole_user_gamecast_admission_partial_play_and_stale_state(self):
        incoming = (0x1234, 0x2345, self.teams, self.teams + 1500, 0x77, 0x88, 0x99, self.STACK, 0x246)
        for caller, outer, mode, stage, admitted in (
                (0x10B95F, 0xC7B58, 2, 8, True), (0xEC00C, 0, 2, 9, True),
                (0x10B95F, 0, 2, 8, False), (0xEC00C, 0, 1, 8, False), (0xEC00C, 0, 2, 6, False)):
            self.write(self.STACK, caller)
            self.write(self.STACK + 28, 0x10B9E0)
            self.write(self.STACK + 52, outer)
            self.write(0xE576A0, mode)
            self.write(0xE576A4, stage)
            state = self.run_code('match_entry', 0x10B280, incoming)
            self.assertEqual(state, incoming)
            self.assertEqual(self.word(self.STACK) != caller, admitted)
            self.assertEqual(self.uc.mem_read(BANK + rules.LABELS['active'], 1), bytes([admitted]))
            target = (BANK + rules.LABELS['completed_catch_scale'] if admitted else SIM + simulator.label_offsets()['pass_scale'])
            self.assertEqual(self.run_code('route_completed_pass', target, incoming), incoming)
            target = BANK + rules.LABELS['supplement'] if admitted else 0x1028B0
            self.assertEqual(self.run_code('medical', target, incoming), incoming)
        self.uc.mem_write(BANK + rules.LABELS['active'], b'\x01')
        self.assertEqual(self.run_code('gamecast_screen_entry', 0x6C780, incoming), incoming)
        self.assertEqual(self.uc.mem_read(BANK + rules.LABELS['active'], 1), b'\0')

    def test_positive_completed_yards_use_the_active_healthy_quarterbacks_accuracy(self):
        stub, measurement, result = 0x3003000, 0x3003100, 0x3003104
        side, player = self.ROOT + 0x9000, self.ROOT + 0xA000
        self.write(0xA9719C, side)
        self.write(side + 8, player)
        target = BANK + rules.LABELS['passing_scale']
        runner = (b'\xd9\x05' + struct.pack('<I', measurement) + rules._call(stub + 6, target)
                  + b'\xd9\x1d' + struct.pack('<I', result))
        self.uc.mem_write(stub, runner)
        incoming = (10, 22, 33, 44, 55, 66, 77, self.STACK, 0x246)

        def measure(accuracy, gain, *, injury=0, status=0, position=0):
            self.uc.mem_write(player + 0x42, bytes([accuracy]))
            self.write(player + 0x20, injury)
            self.write(player + 0x24, status)
            self.uc.mem_write(player + 0x35, bytes([position]))
            self.uc.mem_write(measurement, struct.pack('<f', gain))
            for register, value in zip(self.registers, incoming, strict=True):
                self.uc.reg_write(register, value)
            self.uc.emu_start(stub, stub + len(runner), count=100)
            self.assertEqual(tuple(self.uc.reg_read(r) for r in self.registers), incoming)
            return bytes(self.uc.mem_read(result, 4))

        gain32 = lambda value: struct.unpack('<f', struct.pack('<f', value))[0]
        for rate in (310, 0):
            with self.subTest(medical_rate=rate):
                # Realistic and Custom 0% install the same completed-pass routing and gain.
                bank = rules._link_authored(BANK, SIM, DATA, LINEUP + 0x455)
                rules._configure_tables(bank, rate)
                self.uc.mem_write(BANK, bytes(bank))
                for accuracy in range(101):
                    position = max(0, min(1, (accuracy - 92) / 6))
                    scale = gain32(.982 * (.935 + .130 * position**4))
                    self.assertEqual(measure(accuracy, 16), struct.pack('<f', 16 * scale), accuracy)
        for other in ({'injury': 0x80000000}, {'injury': 1 << 22}, {'status': 1 << 28}, {'position': 1}):
            self.assertEqual(measure(99, 16, **other), struct.pack('<f', 16 * gain32(.982)))
        self.assertEqual(measure(101, 16), struct.pack('<f', 16 * gain32(.982)))
        self.assertEqual(measure(99, -16), struct.pack('<f', -16 * gain32(.982)))
        self.assertEqual(measure(99, 0), struct.pack('<f', 0))

    def test_every_medium_duration_boundary_preserves_machine_state(self):
        for weeks in range(11):
            limit = 177044453 if weeks == 4 else 134321371
            for draw in (0, limit - 1, limit, limit + 1, 0x7FFFFFFF):
                incoming = (0xAA, weeks, 0xCC, draw, 55, 66, 77, self.STACK, 0xA97)
                expected = list(incoming)
                if 4 <= weeks <= 7 and draw >= limit:
                    expected[1] = 3
                self.assertEqual(self.run_code('revise', 0x1027E8, incoming), tuple(expected))


class LocalGameInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = XbeImage(retail_bytes())

    def test_two_complete_bank_layouts_match_the_guarded_310_trial(self):
        # Stability pins (slice 3 plus the stability piece at 0x1C00, its two lines in clinical.S and positions.S and its
        # installed tables; floor 0.35 since the stability review), regenerated by this test's own rules.bank_bytes calls.
        # The slice 3 pins they replace stay
        # as facts of the frozen slice 3 module, which must still link those exact banks.
        from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice3 as slice3
        for bank, expected in ((0x1520000, '752bea54dd1e7244d3df5e072dd20361ea602a7870d2c99cbc8bc602f86ce9bb'),
                               (0x1524000, 'cacafa4e72e414f9c6ea0b94347e8101a3f09a2980f225939907511d14765def'),
                               (BANK, 'baf0968dd8eeb004be6023cee4d91f1b5e84fc0139367921cc143c88cf28a1d0')):
            with self.subTest(frozen_slice3=hex(bank)):
                rate = {'baf0968d': 0}.get(expected[:8], rules.DEFAULT_RATE)
                raw = slice3.bank_bytes(self.image.read, bank, SIM, DATA, LINEUP, rate=rate)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
        # Combined freeze (QB_CHANCE_SCALE 1.06): only the two QB tables move, 606 bytes; at 1.0 these were 7df951ca and
        # 64989e9c (pos3/work/combined-A/freeze/classify.txt).
        pinned = ((0x1520000, '254023945dd0484d2b0c607f781266012ccd1d88a4b53895806a4894a917f56a'),
                  (0x1524000, '9e203b283648c706a8c887e6c4f9d461d03d37d74a4f4eb32873e79f7cf6e823'))
        for bank, expected in pinned:
            with self.subTest(bank=hex(bank)):
                raw = rules.bank_bytes(self.image.read, bank, SIM, DATA, LINEUP)
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                tag = bytes(range(rules.MARK_SIZE))
                tagged = rules.bank_bytes(self.image.read, bank, SIM, DATA, LINEUP, marker=tag)
                self.assertEqual(tagged, raw[:rules.MARK_OFFSET] + tag + raw[rules.MARK_OFFSET + len(tag):])
        zero = rules.bank_bytes(self.image.read, BANK, SIM, DATA, LINEUP, rate=0)
        self.assertEqual(zero, rules.bank_bytes(self.image.read, BANK, SIM, DATA, rate=0))
        self.assertEqual(hashlib.sha256(zero).hexdigest(), '0ff132770f3d0c432a1b262e1933d799c7aa99c5b540427f8abd1882ab322527')

    def test_refuses_foreign_first_middle_or_last_byte_in_every_native_input(self):
        targets = [(at, count) for at, count, _, _ in rules._NATIVE_ABI]
        targets.extend((at, count) for _, at, count, _, _ in rules._LOCAL_FUNCTIONS)
        for at, count in targets:
            for mutated in (at, at + count // 2, at + count - 1):
                with self.subTest(at=hex(at), mutation=hex(mutated)):
                    def read(start, n):
                        data = bytearray(self.image.read(start, n))
                        if start <= mutated < start + n:
                            data[mutated - start] ^= 1
                        return data
                    with self.assertRaisesRegex(ValueError, 'Unrecognized native'):
                        rules.bank_bytes(read, BANK, SIM, DATA, LINEUP)


if __name__ == "__main__":
    unittest.main()
