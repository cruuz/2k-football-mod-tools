"""DESIGN: sourced by batch gdb after boot; all writes are guest RAM only."""
import gdb
import json
import os
from pathlib import Path
import struct
import sys
import time

HERE = Path(os.environ['SD2_LAB_SOURCE'])
sys.path.insert(0, str(HERE))
from fatigue import force_defense
MODE = os.environ['SD2_MODE']
OUT = Path(os.environ['SD2_RUN']) / 'force.json'
repair = json.loads((HERE.parent / 'sd2-evidence/ram-repair.json').read_text())
inf = gdb.selected_inferior()
read = lambda a, n: bytes(inf.read_memory(a, n))
write = lambda a, b: inf.write_memory(a, b)
u32 = lambda a: struct.unpack('<I', read(a, 4))[0]
reg = lambda n: int(gdb.parse_and_eval('$' + n))
state = dict(classification='DESIGN', mode=MODE, forced=False, completed_lineups=0,
             iterator_calls=0, cycle=None, error=None)


def save():
    tmp = OUT.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2) + '\n')
    tmp.replace(OUT)


for site in repair['sites']:
    addr = int(site['va'], 16)
    before, after = bytes.fromhex(site['expected']), bytes.fromhex(site['replacement'])
    if read(addr, len(before)) != before:
        raise RuntimeError('candidate D iterator guard differs')
    if MODE == 'fixed':
        write(addr, after)
        if read(addr, len(after)) != after:
            raise RuntimeError('guest repair readback differs')
state['repair_written'] = MODE == 'fixed'


class Force(gdb.Breakpoint):
    def stop(self):
        if state['forced']:
            return False
        try:
            forced = force_defense(read, write, reg('esp'))
            if forced:
                state.update(forced=True, forced_at=time.time(), target=forced)
                self.enabled = False
                save()
        except Exception as e:
            state['error'] = repr(e)
            save()
            return True
        return False


class Complete(gdb.Breakpoint):
    def stop(self):
        if state['forced']:
            state['completed_lineups'] += 1
            state['last_completion'] = time.time()
            save()
        return False


class Cycle(gdb.Breakpoint):
    def __init__(self):
        super().__init__('*0x1894B3', internal=True)
        self.key, self.seq = None, []

    def stop(self):
        if not state['forced'] or MODE != 'control':
            return False
        sp = reg('esp')
        key = (sp, reg('edx'), u32(sp), u32(sp + 4))
        if key != self.key:
            self.key, self.seq = key, []
        self.seq.append(u32(sp + 8))
        state['iterator_calls'] += 1
        for n in range(1, min(53, len(self.seq) // 3) + 1):
            if self.seq[-n:] == self.seq[-2*n:-n] == self.seq[-3*n:-2*n]:
                state['cycle'] = dict(context=[hex(x) for x in key],
                                      players=[hex(x) for x in self.seq[-n:]],
                                      caller='0x1894b3', iterator='0xe8410',
                                      seconds_since_force=time.time() - state['forced_at'])
                save()
                return True
        save()
        return False


Force('*0x18A6B2', internal=True)  # before native eligibility checks between plays
Complete('*0x18A7A7', internal=True)
if MODE == 'control':
    Cycle()
save()
print('SD2 armed: ' + MODE)
