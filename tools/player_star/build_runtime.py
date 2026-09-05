#!/usr/bin/env python3
"""Rebuild the original star drawing code with GNU i386 binutils (no retail input)."""
from pathlib import Path
import argparse
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'mod_editor/core/nfl2k5_player_star.py'
# Start, capacity, section. Entries and entire spans pass audit.py.
LAYOUT = (
    (0x372D40, 118, 'star_frame'),
    (0x3DDD50, 83, 'star_setup'),
    (0x38B0D0, 83, 'star_position'),
    (0x2C9110, 106, 'star_vertex'),
    (0x31E650, 84, 'star_points'),
)
START = '# BEGIN GENERATED RUNTIME\n'
END = '# END GENERATED RUNTIME\n'


def run(args):
    return subprocess.check_output([str(a) for a in args], text=True)


def build():
    with tempfile.TemporaryDirectory(prefix='player-star-') as tmp:
        d = Path(tmp)
        run(['as', '--32', Path(__file__).with_name('runtime.S'), '-o', d/'runtime.o'])
        script = ['SECTIONS {']
        for va, size, name in LAYOUT:
            script.append(f'.{name} {va:#x} : {{ *(.{name}) }}')
            script.append(f'ASSERT(SIZEOF(.{name}) <= {size}, "{name} exceeds audited capacity")')
        script += ['/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }', '}']
        (d/'link.ld').write_text('\n'.join(script))
        run(['ld', '-m', 'elf_i386', '-T', d/'link.ld', '-o', d/'runtime.elf', d/'runtime.o'])
        symbols = {name: int(va, 16) for va, name in re.findall(
            r'^([0-9a-f]+) [TtRr] (\S+)$', run(['nm', '--defined-only', d/'runtime.elf']), re.M)}
        lines = [START.rstrip(), 'SYMBOLS = {']
        lines += [f'    {name!r}: 0x{va:X},' for name, va in sorted(symbols.items())]
        lines += ['}', '', '# (VA, capacity, original generated code or immutable geometry)', 'CAVES = (']
        for va, size, name in LAYOUT:
            run(['objcopy', '--dump-section', f'.{name}={d/"part.bin"}', d/'runtime.elf'])
            part = (d/'part.bin').read_bytes()
            lines.append(f'    (0x{va:X}, {size}, bytes.fromhex(')
            lines += [f'        "{part[k:k+48].hex()}"' for k in range(0, len(part), 48)]
            lines.append('    )),')
        lines += [')', END.rstrip(), '']
        return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    source = OUT.read_text()
    before, rest = source.split(START)
    old, after = rest.split(END)
    generated = build()
    replacement = before + generated + after
    if args.check:
        if source != replacement:
            raise SystemExit('runtime differs; run tools/player_star/build_runtime.py')
        print('Star runtime is reproducible.')
    else:
        OUT.write_text(replacement)
        print(f'Wrote {OUT.relative_to(ROOT)}')
