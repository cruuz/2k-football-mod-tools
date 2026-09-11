#!/usr/bin/env python3
"""Bounded BASE PPC personnel ladder/record witness. No game or retail output.

Execute the real row picker through 0x8486088C, then the real formation reverse
lookup and category membership test. Only the Xenon 64-bit ABI save/restore
thunks are adapted for Unicorn's PPC32 core; no selection result is stubbed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core import apf2k8_splb_writer as splb
from tools.apf_book_resolution_probe import PE_SHA256, BASE

BOOK, MASTER, STACK, STOP = 0x100000, 0x200000, 0x4ff000, 0x400000


class PersonnelMachine:
    def __init__(self, image: Path, master: bytes):
        import unicorn as u
        from unicorn import ppc_const as r
        data = Path(image).read_bytes()
        if hashlib.sha256(data).hexdigest() != PE_SHA256:
            raise ValueError('Expected the pinned flat BASE PE')
        self.u, self.r = u, r
        self.cpu = x = u.Uc(u.UC_ARCH_PPC, u.UC_MODE_32 | u.UC_MODE_BIG_ENDIAN)
        x.mem_map(BASE, (len(data) + 4095) & ~4095)
        x.mem_write(BASE, data)
        x.mem_map(BOOK, 0x400000)
        x.mem_write(MASTER, master)
        # Actual current-book getter reads this global. No callee is replaced.
        x.mem_write(0x84f3f808, struct.pack('>I', BOOK))
        x.hook_add(u.UC_HOOK_CODE, self._abi)

    def _abi(self, cpu, pc, _size, _data):
        r = self.r
        sp = cpu.reg_read(r.UC_PPC_REG_1)
        if pc == 0x84a89c38:
            cpu.mem_write(sp-16, struct.pack('>Q', cpu.reg_read(r.UC_PPC_REG_31)))
            cpu.reg_write(r.UC_PPC_REG_PC, pc+4)
        elif pc in (0x84a89ca0, 0x84a89cc0):
            cpu.reg_write(r.UC_PPC_REG_31, int.from_bytes(cpu.mem_read(sp-16, 8), 'big'))
            cpu.reg_write(r.UC_PPC_REG_PC, pc+4)
        elif 0x84bd6dc0 <= pc <= 0x84bd6df4:
            first = 18 + (pc - 0x84bd6dc0) // 4
            for reg in range(first, 32):
                cpu.mem_write(sp - 0x10 - (31-reg)*8,
                              struct.pack('>Q', cpu.reg_read(r.UC_PPC_REG_0 + reg)))
            cpu.mem_write(sp-8, struct.pack('>I', cpu.reg_read(r.UC_PPC_REG_12)))
            cpu.reg_write(r.UC_PPC_REG_PC, cpu.reg_read(r.UC_PPC_REG_LR))
        elif 0x84bd6e00 <= pc <= 0x84bd6e44:
            first = 14 + (pc - 0x84bd6e00) // 4
            for reg in range(first, 32):
                cpu.reg_write(r.UC_PPC_REG_0 + reg,
                              int.from_bytes(cpu.mem_read(sp - 0x10 - (31-reg)*8, 8), 'big'))
            cpu.reg_write(r.UC_PPC_REG_PC, int.from_bytes(cpu.mem_read(sp-8, 4), 'big'))

    def install(self, book):
        self.cpu.mem_write(BOOK, book.body)
        self.cpu.mem_write(BOOK + 0x7e0c, struct.pack('>I', MASTER))

    def call(self, address, *args, stop=STOP):
        r, x = self.r, self.cpu
        x.reg_write(r.UC_PPC_REG_1, STACK)
        x.reg_write(r.UC_PPC_REG_LR, STOP)
        for i, arg in enumerate(args, 3):
            x.reg_write(r.UC_PPC_REG_0+i, arg)
        x.emu_start(address, stop, count=50000)
        if x.reg_read(r.UC_PPC_REG_PC) != stop:
            raise AssertionError('Native instruction bound exceeded')
        return x.reg_read(r.UC_PPC_REG_3)

    def picker(self, row):
        self.call(0x84860730, 0x123456, row, 0, stop=0x8486088c)
        pointer = self.cpu.reg_read(self.r.UC_PPC_REG_31)
        if not pointer:
            return None
        category, remainder = divmod(pointer - MASTER - 0x44, 16)
        if remainder or not 0 <= category < splb.CATEGORY_COUNT:
            raise AssertionError('Picker returned an invalid MASTER category')
        return category

    def reachable(self, book, category):
        records = []
        for formation in sorted({r.formation_index for r in book.records if r.populated}):
            pointer = MASTER + 0x244 + formation * 0xb8
            record = self.call(0x84a8a258, BOOK, pointer)
            if not record:
                continue
            if self.call(0x84a8a330, BOOK, pointer, MASTER + 0x44 + category*16):
                index, remainder = divmod(record - BOOK - splb.RECORD_BASE, splb.RECORD_STRIDE)
                assert not remainder and book.records[index].populated
                records.append(index)
        return records


def witness(image, master, before, after):
    machine = PersonnelMachine(image, master)
    result = []
    for book in (before, after):
        machine.install(book)
        selections = []
        for row in range(28):
            category = machine.picker(row)
            records = machine.reachable(book, category) if category is not None else []
            selections.append({'requested_row': row, 'category': category, 'records': records})
        result.append(selections)
    retired = set(splb.book_category_rows(before.body)) - set(splb.book_category_rows(after.body))
    for old, new in zip(*result):
        assert new['category'] not in retired
        if old['records']:
            assert new['records'], f"New null record path for row {new['requested_row']}"
    return {'status': 'PROVED bounded native BASE; gameplay UNWITNESSED',
            'image_sha256': PE_SHA256, 'abi_adapter': '64-bit register save/restore thunks only',
            'native_functions': ['84860730..8486088C', '84A8B438', '84A89B40',
                                 '84A89680', '84A89D60', '84A8A258', '84A8A330'],
            'before': result[0], 'after': result[1], 'retired_categories': sorted(retired),
            'new_null_record_paths': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body
    book = splb.read_book(args.index, 130)
    changes = [splb.TrailerReplace(130, r.record_index, 69, 8)
               for r in book.records if r.populated and r.category_index == 6]
    compiled = splb.compile_book(book, changes)
    after = splb.parse_book(compiled.replacement, 130)
    report = witness(args.image, read_master_play_body(args.index), book, after)
    report['ladder'] = compiled.report['personnel_ladder']
    report['verification'] = splb.verify_book(book.body, after.body, changes)
    with args.report.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    print('PASS: Queens retired; 28 native row requests; no new null record path')


if __name__ == '__main__':
    main()
