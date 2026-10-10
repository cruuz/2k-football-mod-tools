#!/usr/bin/env python3
"""Read-only, bounded native replays on extracted FRZ disc resources.

Fixtures are not a whole game. No Xbox kernel, emulator, or disc build is used.
"""
from collections import Counter, deque
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
import unicorn as uc
from unicorn import x86_const as x


class Lineup:
    TEAM, PLAYERS, CHART, DESC = 0x2000000, 0x2001000, 0x2008000, 0x2009000
    STACK, STOP = 0x3008000, 0x3009000

    def __init__(self, payload):
        self.u = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        end = (max(s.end for s in image.sections) + 4095) & ~4095
        self.u.mem_map(0x10000, end - 0x10000)
        for s in image.sections:
            if s.raw_size:
                self.u.mem_write(s.start, payload[s.raw:s.raw+s.raw_size])
        self.u.mem_map(self.TEAM, 0x10000)
        self.u.mem_map(0x3000000, 0x10000)
        self.trace = deque(maxlen=40)

    def put(self, a, v):
        self.u.mem_write(a, struct.pack('<I', v & 0xffffffff))

    def call(self, pc, args=(), count=100000, **regs):
        self.trace.clear()
        self.u.mem_write(self.STACK, struct.pack('<'+'I'*(len(args)+1), self.STOP, *args))
        defaults = dict(esp=self.STACK, ebp=0, eax=0, ebx=0, ecx=0, edx=0,
                        esi=0, edi=0, eflags=0x202, fpcw=0x37f, fptag=0xffff, fpsw=0)
        defaults.update(regs)
        for name, value in defaults.items():
            self.u.reg_write(getattr(x, 'UC_X86_REG_'+name.upper()), value)
        self.u.emu_start(pc, self.STOP, count=count)
        eip = self.u.reg_read(x.UC_X86_REG_EIP)
        if eip != self.STOP:
            raise RuntimeError(f'budget {count} expired at {eip:#x}; tail {[hex(a) for a in self.trace]}')
        if self.u.reg_read(x.UC_X86_REG_ESP) != self.STACK + 4 + len(args)*4:
            raise RuntimeError(f'stack imbalance in {pc:#x}')
        return self.u.reg_read(x.UC_X86_REG_EAX)

    def team(self, document, team, state='rested', side=1):
        self.u.mem_write(self.TEAM, bytes(0x10000))
        self.u.mem_write(self.TEAM, bytes(document.body[team.offset:team.offset+rr.TEAM_SIZE]))
        self.players = []
        for i, p in enumerate(document.team_players(team.index)):
            addr = self.PLAYERS + i * rr.PLAYER_SIZE
            self.players.append(addr)
            self.put(self.TEAM + i*4, addr)
            raw = bytearray(p.record.encode())
            raw[0x34] = side
            if state == 'injured':
                struct.pack_into('<H', raw, 0x28, struct.unpack_from('<H', raw, 0x28)[0] | 0x20)
            self.u.mem_write(addr, bytes(raw))
            work = self.TEAM + 0xa000 + i*0x40
            self.put(addr+0x30, work)
            self.put(work+4, work+0x20)
            self.u.mem_write(work+0x24, struct.pack('<f', 0.05 if state == 'tired' else 1.0))
        self.call(0xE80D0, (0, 0), ecx=self.TEAM, edx=self.CHART, count=1000000)
        # Native home/away chart getters used by the real eligibility caller.
        chart = bytes(self.u.mem_read(self.CHART, 0x334))
        for address in (0xB336F4, 0xB33A28):
            relocated = bytearray(chart)
            for offset in range(0x9c, 0x10c, 4):
                pointer = struct.unpack_from('<I', chart, offset)[0]
                struct.pack_into('<I', relocated, offset, pointer-self.CHART+address)
            self.u.mem_write(address, bytes(relocated))
        for address in (0xE60194, 0xE601A4):
            self.put(address, 5)
            self.put(address+4, 16)
            self.put(address+8, 7)

    def stream(self, descriptor, slot, tier):
        self.u.mem_write(self.DESC, descriptor)
        p = self.call(0xE81D0, (slot,tier), ecx=self.CHART, edx=self.DESC)
        seq = []
        while p:
            if p in seq or len(seq) > len(self.players):
                raise RuntimeError(f'candidate cycle {p:#x}: {[hex(a) for a in seq]}')
            if p not in self.players:
                raise RuntimeError(f'foreign player {p:#x}')
            seq.append(p)
            p = self.call(0xE8410, (slot,tier,p), ecx=self.CHART, edx=self.DESC)
        return len(seq)


def lineup(directory, output, teams=None):
    payload = (directory/'default.xbe').read_bytes()
    raw = (directory/'entry5.bin').read_bytes()[32:]
    doc = rr.load_body(raw, scheme='one_pool')
    m = Lineup(payload)
    result = dict(xbe_sha256=hashlib.sha256(payload).hexdigest(), roster_sha256=hashlib.sha256(raw).hexdigest(),
                  fixture='Disc main roster records and ranks; native depth-chart builder. All candidates rejected/consumed, so tired and assigned exhaustion is stronger than early acceptance. Injury bit 0x20. Both squad sides.', teams=[])
    aliases = {'ARI':'ARZ','LAC':'SD','LV':'OAK','LAR':'STL'}
    for t in doc.teams[:32]:
        key = aliases.get(t.abbreviation, t.abbreviation)
        if teams and key not in teams:
            continue
        book_raw = (directory/f'{key}.play').read_bytes()
        body = book_raw[32:]
        book = ip.parse_playbook_resource(book_raw)
        row = dict(team=key, cases=0, peak=0, faults=[])
        for side in (0,1):
            for state in ('rested','tired','injured'):
                m.team(doc,t,state,side)
                cache = {}
                for f in book.formations:
                    ci = lib.formation_category(body,f.index)
                    descriptor = body[ip.CATEGORY_BASE+ci*16:ip.CATEGORY_BASE+(ci+1)*16]
                    for slot in range(11):
                        for tier in (0,1,2,6):
                            row['cases'] += 1
                            try:
                                ck = (descriptor,slot,tier)
                                if ck not in cache:
                                    cache[ck] = m.stream(descriptor,slot,tier)
                                n = cache[ck]
                                row['peak'] = max(row['peak'],n)
                            except Exception as exc:
                                row['faults'].append(dict(side=side,state=state,formation=f.index,name=f.name,
                                    category=ci,descriptor=descriptor.hex(),slot=slot,tier=tier,error=str(exc)))
        result['teams'].append(row)
        output.write_text(json.dumps(result,indent=1)+'\n')
        print(key,row['cases'],len(row['faults']),row['peak'],flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('directory',type=Path)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--team',action='append')
    args = ap.parse_args()
    result = lineup(args.directory,args.out,args.team)
    return int(any(t['faults'] for t in result['teams']))


if __name__ == '__main__':
    sys.exit(main())
