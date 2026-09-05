"""Bounded native arithmetic parity, not an emulator or game execution.

Read only a SHA-pinned retail XBE. Reassemble the salary helpers for x64,
changing pointer/stack widths only; preserve their 32-bit integer and x87/SSE
arithmetic. No retail code/data is stored in the repository. Skip elsewhere.
"""
from pathlib import Path
import hashlib
import itertools
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_practice_squad as ps

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)' / 'default.xbe'


def assembly(payload, capstone):
    lines = ['.intel_syntax noprefix', '.text', '.global native_salary', 'native_salary:',
             'push rbx', 'push rsi', 'push rdi', 'push rbp', 'mov rcx, rdi',
             'call L_e6380', 'pop rbp', 'pop rdi', 'pop rsi', 'pop rbx', 'ret',
             '.global native_bonus', 'native_bonus:', 'movzx ecx, word ptr [rdi+10]',
             'mov edx, dword ptr [rdi+36]', 'mov eax, edx', 'shr eax, 24', 'and eax, 15',
             'push rax', 'shr edx, 20', 'and edx, 15', 'call L_e6020', 'ret']
    # E6040 ends before its eight-entry jump table. Data never becomes instructions.
    for start, end in ((0xe3f10, 0xe3f19), (0xe5ff0, 0xe5ff6), (0xe6020, 0xe6037),
                       (0xe6040, 0xe635a), (0xe6380, 0xe63af)):
        for instruction in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(
                payload[start-0x10000:end-0x10000], start):
            op, mnemonic = instruction.op_str, instruction.mnemonic
            if mnemonic in ('push', 'pop'):
                op = re.sub(r'\be(ax|bx|cx|dx|si|di|bp)\b', r'r\1', op)
            op = re.sub(r'\[esp \+ (0x[0-9a-f]+|[0-9]+)\]',
                        lambda match: f'[rsp + {int(match[1], 0)*2}]', op).replace('[esp]', '[rsp]')
            op = op.replace('[ecx +', '[rcx +').replace('rcx + ecx*4', 'rcx + rcx*4')
            if mnemonic == 'ret' and op:
                op = str(int(op, 0)*2)
            if mnemonic == 'call' or (mnemonic.startswith('j') and op.startswith('0x')):
                op = 'L_' + op[2:]
            if mnemonic == 'jmp' and 'ptr' in op:
                op = 'QWORD PTR [rbx*8 + curve_table]'
            op = op.replace('[0x4e4184]', '[half_value]').replace('[0x4e419c]', '[one_value]')
            if mnemonic == 'fsubp':
                op = 'st(1), st(0)'
            lines.append(f'L_{instruction.address:x}: {mnemonic} {op}')
    lines.extend(['.section .rodata', 'half_value: .float 0.5', 'one_value: .float 1.0',
                  'curve_table: .quad ' + ','.join(f'L_{value:x}' for value in struct.unpack_from('<8I', payload, 0xd635c)),
                  '.section .note.GNU-stack,"",@progbits'])
    return '\n'.join(lines) + '\n'


DRIVER = r'''
#include <stdio.h>
#include <stdint.h>
static unsigned char record[84];
extern int native_salary(unsigned char *);
extern int native_bonus(unsigned char *);
int main(void) {
    while (fread(record, 84, 1, stdin) == 1) {
        int result[2] = {native_salary(record), native_bonus(record)};
        if (fwrite(result, 8, 1, stdout) != 1) return 1;
    }
    return 0;
}
'''


class NativeSalaryTests(unittest.TestCase):
    def test_all_curves_lengths_bonus_and_truncation_against_native_instructions(self):
        if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
            self.skipTest('optional native arithmetic probe requires Linux x64; portable numeric cases run separately')
        if not shutil.which('gcc'):
            self.skipTest('optional native arithmetic probe requires gcc and GNU assembler')
        if not XBE.is_file():
            self.skipTest('SHA-pinned retail default.xbe is absent')
        try:
            import capstone
        except ImportError:
            self.skipTest('native arithmetic extraction requires capstone')
        payload = XBE.read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), ps.RETAIL_SHA256)
        cases = [(value, kind, bonus, year, length)
                 for value, kind, bonus, length in itertools.product(
                     (0, 1, 7, 99, 1234, 65535), range(8), (0, 1, 5, 15), range(1, 16))
                 for year in range(length+1)]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root/'math.S').write_text(assembly(payload, capstone))
            (root/'driver.c').write_text(DRIVER)
            result = subprocess.run(['gcc', '-no-pie', str(root/'driver.c'), str(root/'math.S'), '-o', str(root/'math')],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            with (root/'input').open('wb') as stream:
                for value, kind, bonus, year, length in cases:
                    record = bytearray(84)
                    struct.pack_into('<H', record, 10, value)
                    struct.pack_into('<I', record, 36, (length-year) | kind << 16 | bonus << 20 | length << 24)
                    stream.write(record)
            with (root/'input').open('rb') as stream:
                native = subprocess.run([str(root/'math')], stdin=stream, capture_output=True, timeout=30)
            self.assertEqual(native.returncode, 0, native.stderr.decode())
            outputs = list(struct.iter_unpack('<ii', native.stdout))
            self.assertEqual(len(outputs), len(cases))
            for case, expected in zip(cases, outputs):
                value, kind, bonus, year, length = case
                actual = (ps.contract_base_salary(*case), ps.contract_bonus_salary(value, bonus, length))
                self.assertEqual(actual, expected, case)
            self.assertEqual(len(cases), 25920)


if __name__ == '__main__':
    unittest.main()
