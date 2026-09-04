#!/usr/bin/env python3
"""Rebuild our freestanding runtime; no disc or proprietary bytes are input.

Requires GNU gcc/binutils with i386 support. Normal Studio users do not need
these tools: the checked-in generated Python payload is used on every OS.
"""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'mod_editor/core/nfl2k5_practice_squad_runtime.py'
# Entire spans pass the conservative reference scan, including their entries.
CAVES = ((0x2890F0, 1939), (0x374111, 651), (0x3BA610, 592),
         (0x3DCB20, 381), (0x3BABE0, 333))

def run(args):
    return subprocess.check_output([str(x) for x in args], text=True)

def build():
    with tempfile.TemporaryDirectory(prefix='practice-squad-') as folder:
        d = Path(folder)
        source = Path(__file__).parent
        run(['gcc', '-m32', '-Os', '-ffreestanding', '-fno-builtin', '-fno-pic', '-fno-pie',
             '-fno-stack-protector', '-fno-asynchronous-unwind-tables', '-fno-unwind-tables',
             '-ffunction-sections', '-fdata-sections', '-mpreferred-stack-boundary=2', '-mno-sse',
             '-mno-mmx', '-Wall', '-Wextra', '-Werror', '-c', source / 'runtime.c', '-o', d / 'c.o'])
        run(['as', '--32', source / 'runtime.S', '-o', d / 's.o'])
        pieces = []
        for obj in ('c.o', 's.o'):
            for name, size in re.findall(r'^\s*\d+ (\.(?:text|rodata)\S*)\s+([0-9a-f]+)',
                                         run(['objdump', '-h', d / obj]), re.M):
                if int(size,16): pieces.append((int(size,16), obj, name))
        bins = [[] for _ in CAVES]
        used = [0 for _ in CAVES]
        for size, obj, name in sorted(pieces, reverse=True):
            for i, (va, capacity) in enumerate(CAVES):
                aligned = (va + used[i] + 3) & ~3
                if aligned + size <= va + capacity:
                    bins[i].append((aligned, size, obj, name)); used[i] = aligned + size - va
                    break
            else: raise RuntimeError(f'no audited cave has room for {name} ({size} bytes)')
        ld = ['SECTIONS {']
        for i, (va, capacity) in enumerate(CAVES):
            if not bins[i]: continue
            ld.append(f'.cave{i} {va:#x} : {{')
            for address, size, obj, name in bins[i]:
                ld.append(f'. = {address-va}; {d/obj}({name})')
            ld.append('}')
        ld.append('/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) } }')
        (d/'link.ld').write_text('\n'.join(ld))
        run(['ld', '-m', 'elf_i386', '-T', d/'link.ld', '-o', d/'runtime.elf', d/'c.o', d/'s.o'])
        # No mutable runtime state can slip into a .data/.bss segment.
        assert not re.search(r'\.(?:data|bss)\s+0*[1-9a-f]', run(['objdump','-h',d/'runtime.elf']))
        symbols = {}
        for address, kind, name in re.findall(r'^([0-9a-f]+) ([TtRr]) (\S+)$',
                                             run(['nm','--defined-only',d/'runtime.elf']), re.M):
            symbols[name] = int(address,16)
        lines = ['"""Generated original machine code. See tools/practice_squad/build_runtime.py."""',
                 '', 'SYMBOLS = {']
        lines += [f'    {name!r}: 0x{va:X},' for name, va in sorted(symbols.items())]
        lines += ['}', '', '# (VA, audited capacity, original code bytes)', 'CAVES = (']
        for i,(va,capacity) in enumerate(CAVES):
            if not bins[i]: continue
            run(['objcopy','--dump-section',f'.cave{i}={d / "code.bin"}', d/'runtime.elf'])
            data=(d/'code.bin').read_bytes()
            lines.append(f'    (0x{va:X}, {capacity}, bytes.fromhex(')
            lines.extend(f'        "{data[k:k+48].hex()}"' for k in range(0,len(data),48))
            lines.append('    )),')
        lines += [')','']
        return '\n'.join(lines)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args=parser.parse_args()
    text=build()
    if args.check:
        if not OUT.is_file() or OUT.read_text()!=text: raise SystemExit('runtime differs; run build_runtime.py')
        print('Runtime is reproducible.')
    else:
        OUT.write_text(text)
        print(f'Wrote {OUT.relative_to(ROOT)}')
