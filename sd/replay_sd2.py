#!/usr/bin/env python3
"""PROVED OFFLINE: execute D's captured native code. Never starts xemu.

python3 sd/replay_sd2.py [--sweep]
Reads main/stall-candD/watch-end.bin; writes only sd/sd2-evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), '/media/noah/Storage/.b76-research/k1/harness']
from r4_ramscan import Ram
from mod_editor.core import nfl2k5_lineup_iterator as code
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_MEM_UNMAPPED, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_EIP

CAPTURE = Path('/media/noah/Storage/.b76-research/main/stall-candD/watch-end.bin')
OUT = ROOT / 'sd/sd2-evidence'
ROSTER, DESC, STACK, LINEUP = 0xB336F4, 0xB7F40C, 0xD0046A88, 0xD0046B0C
RAM = None


def pack(x):
    return struct.pack('<I', x)


class Replay:
    def __init__(self, fixed=True):
        global RAM
        if RAM is None:
            RAM = Ram(CAPTURE.read_bytes(), 0xF000)
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.pages = set()
        self.u.hook_add(UC_HOOK_MEM_UNMAPPED, self.page)
        self.u.mem_map(0x10000000, 0x20000)
        if fixed:
            self.patch(code.VA, code.replacement())

    def page(self, u, access, addr, size, value, user):
        for p in range(addr & ~4095, (addr + size + 4095) & ~4095, 4096):
            if p not in self.pages:
                data = RAM.vread(p, 4096)
                if data is None:
                    raise RuntimeError(f'unmapped captured page {p:#x}')
                u.mem_map(p, 4096)
                u.mem_write(p, data)
                self.pages.add(p)
        return True

    def patch(self, addr, data):
        self.page(self.u, 0, addr, len(data), 0, None)
        self.u.mem_write(addr, data)

    def call(self, addr, ecx, edx, args, bound=100000):
        u = self.u
        u.mem_write(0x10010000, struct.pack('<' + 'I' * (1 + len(args)), 0x10000000, *args))
        for reg, val in [(UC_X86_REG_ESP, 0x10010000), (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx)]:
            u.reg_write(reg, val)
        u.emu_start(addr, 0x10000000, count=bound)
        assert u.reg_read(UC_X86_REG_EIP) == 0x10000000, 'instruction bound'
        assert u.reg_read(UC_X86_REG_ESP) == 0x10010004 + 4 * len(args), 'stack ABI'
        return u.reg_read(UC_X86_REG_EAX)

    def players(self):
        team = RAM.v32(ROSTER)
        return [RAM.v32(team + i * 4) for i in range(53)]

    def roster_state(self, state='rested', profile='modern'):
        lbs = []
        for i, p in enumerate(self.players()):
            enum = RAM.vread(p + 0x35, 1)[0]
            if enum in (10, 11):
                lbs.append(p)
                self.patch(p + 0x35, bytes([10 if profile == 'legacy' or (profile == 'mixed' and i % 2) else 11]))
            fatigue = RAM.v32(RAM.v32(p + 0x30) + 4) + 4
            value = 0.05 if state == 'tired' or (state == 'mixed' and i % 2) else 1.0
            self.patch(fatigue, struct.pack('<f', value))
        if state == 'empty':
            # Native counts are adjacent pointers, so one shared empty tail
            # makes every list empty without touching the roster itself.
            tail = RAM.v32(ROSTER + 0x108)
            self.patch(tail, b'\xff')
            self.patch(ROSTER + 0x9C, pack(tail) * 28)
        return lbs


def outer(fixed, rested=False, profile='modern', primary15=False):
    m = Replay(fixed)
    if rested:
        m.roster_state(profile=profile)
    if primary15:
        desc = bytearray(RAM.vread(DESC, 16))
        desc[5:] = bytes((v & ~31) | 15 if v & 31 == 14 else v for v in desc[5:])
        m.patch(DESC, bytes(desc))
    u = m.u
    m.page(u, 0, STACK, 4096, 0, None)
    esp, start = (0xD0046AC0, 0x18A716) if rested else (STACK, 0x1893E0)
    if rested:
        m.patch(LINEUP, bytes(44))
    for reg, val in [(UC_X86_REG_ESP, esp), (UC_X86_REG_EBP, 6), (UC_X86_REG_ESI, 0xB31624)]:
        u.reg_write(reg, val)
    candidates, steps = [], [0]
    def trace(u, addr, size, data):
        steps[0] += 1
        if addr == 0x1893E0:
            candidates.append(hex(u.reg_read(UC_X86_REG_ESI)))
            if len(candidates) > 200:
                u.emu_stop()
        if addr == 0x18A7A7:
            u.emu_stop()
    u.hook_add(UC_HOOK_CODE, trace)
    u.emu_start(start, 0, count=200000)
    return dict(returned=u.reg_read(UC_X86_REG_EIP) == 0x18A7A7,
                instructions=steps[0], candidates=candidates,
                lineup=[hex(x) for x in struct.unpack('<11I', u.mem_read(LINEUP, 44))])


def sweep():
    rows, cases, max_candidates = {}, 0, 0
    for profile in ('modern', 'mixed', 'legacy'):
        for state in ('rested', 'tired', 'assigned', 'mixed', 'empty'):
            m = Replay()
            m.roster_state(state, profile)
            bits = struct.unpack('<19I', RAM.vread(0x515778, 76))
            for kind in range(19):
                peak = 0
                for rank in (0, 1, 2, 3):
                    m.patch(DESC + 5, bytes([kind | rank << 5]))
                    for tier in (0, 1, 2, 6):
                        for mask in {bits[kind], 0x7FFFF, 0x4000, 0x8000, 0xC000, 0}:
                            m.patch(0xAC26B8 + 13 * 44, pack(mask))
                            p = m.call(0xE81D0, ROSTER, DESC, [0, tier])
                            seq = []
                            while p:
                                assert p not in seq, (profile, state, kind, rank, tier, hex(mask), 'duplicate')
                                seq.append(p)
                                assert len(seq) <= 53
                                p = m.call(code.VA, ROSTER, DESC, [0, tier, p])
                            # Consume the entire stream, even if eligibility
                            # would accept an earlier member. Assigned means
                            # rejecting each candidate by caller membership;
                            # this predicate is independent of the iterator.
                            if not seq:
                                assert m.call(code.VA, ROSTER, DESC, [0, tier, m.players()[0]]) == 0
                            peak = max(peak, len(seq))
                            cases += 1
                rows[f'{profile}/{state}/{kind}'] = peak
                max_candidates = max(max_candidates, peak)
    return dict(cases=cases, max_candidates=max_candidates, max_calls=54,
                instructions_per_call_bound=100000, peaks=rows,
                states='Energies written for rested/tired/mixed; assigned consumes and rejects every candidate. Empty clears native list extents. No native game callees mocked.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sweep', action='store_true')
    args = ap.parse_args()
    Replay()
    assert RAM.vread(code.VA, code.SIZE) == code.RETAIL
    report = dict(classification='PROVED OFFLINE', capture_sha256=hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),
                  replacement_sha256=hashlib.sha256(code.replacement()).hexdigest(),
                  captured_before=outer(False), captured_after=outer(True), normal=[])
    assert not report['captured_before']['returned']
    after = report['captured_after']
    assert after['returned'] and len(set(after['lineup'])) == 11 and '0x0' not in after['lineup']
    for profile in ('modern', 'mixed', 'legacy'):
        for primary15 in (False, True):
            before, after = outer(False, True, profile, primary15), outer(True, True, profile, primary15)
            assert before['returned'] and after['returned'], (profile, primary15, before, after)
            assert before['lineup'] == after['lineup'], (profile, primary15, before, after)
            report['normal'].append(dict(profile=profile, primary15=primary15, before=before, after=after))
    if args.sweep:
        report['sweep'] = sweep()
    OUT.mkdir(exist_ok=True)
    (OUT / 'replay.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PROVED OFFLINE: captured caller repaired; six rested full-lineup comparisons identical;',
          report.get('sweep', {}).get('cases', 0), 'bounded sweep cases.')


if __name__ == '__main__':
    main()
