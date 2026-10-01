"""PROVED OFFLINE: bounded native roster load, lineup list build and picker.

No game routine is stubbed. Synthetic availability=all and no substitutions,
injuries, assigned teammates or fatigue. Auto-depth runs with a 32-club league
count and CPU management enabled. This is not a complete match witness.
"""
from __future__ import annotations
import argparse
import json
import struct
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dc.import_depth import OUT, ALIASES, sha, rr, player_info, latest_rows, SNAPSHOT, matcher
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes
from mod_editor.core import nfl2k5_depth_locks as locks, nfl2k5_returner_fix as fix
from mod_editor.core import nfl2k5_modern_positions as modern, nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_depth_chart_rows as rows

# The native 0x4f5930 table maps kind 4 even ordinals to KR, odd to PR.
PICKS={'KR1':(4,0),'KR2':(4,2),'PR':(4,1),'K':(2,0),'P':(1,0),'LS':(6,1),'H':(3,0)}
CHART={'KR1':(0,254,0),'KR2':(1,254,0),'PR':(0,253,0), 'K':(0,1,0),'P':(0,2,0),'LS':(0,12,2)}

class Probe:
    def __init__(self, xbe, body):
        self.doc=rr.RosterDocument(body)
        self.m=m=Machine(xbe,trace_writes=False)
        self.calls={hex(a):0 for a in (0xc0500,0x243790,0x2bdcf0,0xe7c50,0xe8790)}
        for address in (0xc0500,0x243790,0x2bdcf0,0xe7c50,0xe8790):
            def count(_uc, address, _size, _data):
                self.calls[hex(address)]+=1
            m.uc.hook_add(m.u.UC_HOOK_CODE,count,begin=address,end=address)
        self.base=m.ARENA+0x300
        m.uc.mem_write(self.base,body)
        m.fixup_roster(self.base+0x40)
        self.load_calls=dict(self.calls)
        # Only the 32 NFL clubs enter this bounded franchise-style sort.
        m.put(m.root+0x18,32)
        m.put(0xe60140,1)
        self.context=m.ARENA+0x150000
        self.assigned=self.context+0x1000
        m.put(0xac26b8,0)
    def info(self,address):
        if not address:return None
        p=self.doc.by_offset.get(address-self.base)
        if not p:raise AssertionError(f'unknown roster pointer {address:#x}')
        word=struct.unpack('<H',self.m.uc.mem_read(address+0x28,2))[0]
        return {**player_info(p),'depth_rank':word>>10&7,'depth_side':word>>13&7}
    def picks(self,team):
        m=self.m
        ptr=m.team_base+team*500
        # Native dense lists include actual roster indices, rank/side and H/KR/PR.
        m.call(0xe80d0,ecx=ptr,edx=self.context,args=(0,1),budget=1000000)
        m.put(self.context+4,0)
        return {role:self.info(m.call(0xe8790,ecx=self.context,
                          args=(0,0,self.assigned,0,0,kind,ordinal),budget=200000))
                for role,(kind,ordinal) in PICKS.items()}
    def table(self):
        result=[]
        for team in self.doc.teams[:32]:
            ptr=self.m.team_base+500*team.index
            raw=self.m.uc.mem_read(ptr,500)
            result.append({'team':ALIASES.get(team.abbreviation,team.abbreviation), 'team_index':team.index,
                           'stored':{role:{'slot':raw[off], 'player':self.info(struct.unpack_from('<I',raw,raw[off]*4)[0]) if raw[off]<raw[0x11c] else None}
                                     for role,off in rr.SPECIAL_TEAM_OFFSETS.items()},
                           'chart':{role:self.info(self.m.call(0x242ae0,edx=ptr,args=args)) for role,args in CHART.items()},
                           'picked':self.picks(team.index)})
        return result
    def sort(self):
        self.m.call(0x2bdcf0,budget=100000000)

def minimal_xbe():
    data=retail_bytes()
    for mod in (fix,modern,pools,rows,locks):data=mod.apply(data)[0]
    return data

def run(xbe=None,body=None,output=ROOT/'dc/proof/native.json',sorts=3):
    xbe=minimal_xbe() if xbe is None else xbe
    after=(OUT/'candidate_C_dc.rost').read_bytes() if body is None else body
    before=(OUT/'candidate_C_before.rost').read_bytes()
    old,new=Probe(xbe,before),Probe(xbe,after)
    report={'evidence':'PROVED OFFLINE','xbe_sha256':sha(xbe),'before_body_sha256':sha(before),'after_body_sha256':sha(after),
            'substituted_routines':[], 'boundary':__doc__, 'before':old.table(),'after':new.table(), 'sorts':[]}
    report['load_calls']={'before':old.load_calls,'after':new.load_calls}
    # Every selection, including the documented exhausted-source fallbacks.
    imported=json.loads((ROOT/'dc/proof/import.json').read_text())
    for row,desired in zip(report['after'],imported['teams']):
        for role in PICKS:
            source='KR' if role.startswith('KR') else 'PK' if role=='K' else role
            wanted=desired['roles'][source]['chosen'][1 if role=='KR2' else 0]
            assert row['picked'][role]['index']==wanted['index'],(row['team'],role,row['picked'][role],wanted)
    print('PROVED OFFLINE: native load and 32-team picks passed',flush=True)
    old.sort()
    report['before_after_auto_sort']=old.table()
    for n in range(sorts):
        new.sort();table=new.table()
        for a,b in zip(report['after'],table):
            for role in PICKS:
                assert a['picked'][role]['index']==b['picked'][role]['index'],(n,a['team'],role,a['picked'][role],b['picked'][role])
        report['sorts'].append({'pass':n+1,'teams':table})
        print(f'PROVED OFFLINE: sort {n+1}, all 224 specialist picks retained',flush=True)
    report['native_call_counts']={'before':old.calls,'after':new.calls}
    output.write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    run()
