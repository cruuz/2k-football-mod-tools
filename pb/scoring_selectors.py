#!/usr/bin/env python3
"""PROVED OFFLINE: real selector/policy replay with explicit synthetic world inputs.

DESIGN: state dimensions are factored, not a Cartesian proof of a whole game.
All PLAY-indexed scorer arguments are exhausted separately by scoring_sweep.py.
No selector, category policy, compatibility, trajectory or matchup is stubbed.
"""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import random
import struct
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_play_scoring as s, nfl2k5_playbook_inspector as ip
from pb.verify_league import OuterImage,BOOK_ENTRIES

class World(s.NativeScorer):
    def __init__(self,payload):
        super().__init__(payload)
        self.defense=s.SOURCE+0x1c000
        self.m.mem_write(self.defense,bytes(self.m.mem_read(s.TEAM,0x100)))
        self.put(self.defense,s.TEAM);self.put(s.TEAM,self.defense)
        self.put(0xe60284,self.defense);self.put(self.defense+12,s.META+0x300)
        self.put(self.defense+8,s.META+0x500);self.put(s.META+0x50c,s.DIRECTION)
        self.put(0xe6028c,s.STATE+0x500);self.put(0xe60294,s.STATE+0x600)
        self.fput(s.STATE+0x610,25);self.fput(0xbf1484,.5);self.fput(0xbf1244,.5)
        self.fput(0xbf1240,120);self.fput(0xbf1480,120);self.fput(0xbf16f8,.5)
        self.put(s.META+0x100,s.META+0x800)
        self.put(s.META+0x300,s.META+0x900)
        # Kicker capacity is an environmental roster-derived scalar.
        def fg(u,a,n,d):
            self.environment_calls['0x18b120']+=1
            self.fput(s.STOP+0x80,50*91.44)
            u.mem_write(s.STOP+0x90,b'\xd9\x05'+struct.pack('<I',s.STOP+0x80)+b'\xc3')
            u.reg_write(self.r.UC_X86_REG_EIP,s.STOP+0x90)
        self.m.hook_add(self.ucmod.UC_HOOK_CODE,fg,begin=0x18b120,end=0x18b120)
        self.native_start=self.m.emu_start
        self.m.emu_start=lambda a,b,**kw:self.native_start(a,b,count=20000000)
        self.visits=Counter()
        for pc in (0x20b820,0x20b400,0x2093f0,0x20a240,0x2081b0,0x20a7f0,0x20aa40,
                   0x2096a0,0x208820,0x207bf0,0x203f20,0x205660,0x2815f0,0x281620):
            self.m.hook_add(self.ucmod.UC_HOOK_CODE,lambda u,a,n,d:self.visits.update([hex(a)]),begin=pc,end=pc)

    def load(self,raw):
        self.book=ip.parse_playbook_resource(raw)
        self.m.mem_write(s.SOURCE,raw[32:]);self.call(0x161e30,ecx=s.SOURCE,edx=0)
        self.put(s.TEAM+0x20,s.BOOK);self.put(self.defense+0x20,s.BOOK)
        for play in self.book.plays:self.call(0x1a9a80,ecx=s.BOOK+ip.PLAY_BASE+play.index*96)
        # Clock policy reuses the team's saved formation/play. A real team
        # initializes these when its book loads; zero is not a legal fixture.
        formation=next(f for f in self.book.formations if ((self.get(s.BOOK+ip.FORMATION_BASE+f.index*ip.FORMATION_SIZE+4)>>8)&63) in (0,1,2,3))
        fv=s.BOOK+ip.FORMATION_BASE+formation.index*ip.FORMATION_SIZE
        play=next(p for p in self.book.plays if self.call(0xe1440,ecx=s.BOOK,edx=s.BOOK+ip.PLAY_BASE+p.index*96,args=(fv,)))
        pv=s.BOOK+ip.PLAY_BASE+play.index*96
        for offset in (0x144,0x14c):self.put(s.META+offset,fv)
        for offset in (0x130,0x134):self.put(s.META+offset,pv)
        rng=random.Random(20260925)
        self.put(0xe5fca0,54);self.put(0xe5fca4,23)
        for index in range(110):self.put(0xe5fca8+4*index,rng.getrandbits(32))
        for base in (0xbf1090,0xbf1168,0xbf12d0,0xbf13a8):self.m.mem_write(base,bytes(216))
        self.visits.clear();self.counts.clear();self.environment_calls.clear()

    def configure(self,down=1,distance=10,yard=50,margin=0,quarter=2,seconds=300,direction=1,phase=4):
        self.put(s.STATE+4,down);self.fput(s.STATE+0x18,(yard-50)*91.44*direction)
        self.fput(s.STATE+0x28,(yard-50+distance)*91.44*direction)
        self.fput(s.DIRECTION+4,direction);self.put(s.META,40+margin);self.put(s.META+0x500,40)
        self.put(s.META+4,3);self.put(s.META+0x504,3)
        self.put(0xe602b4,phase);self.put(0xe602c4,quarter);self.fput(s.STATE+0x510,seconds)
        self.fput(0xe602b0,0)
        for a in (0xbf16fc,0xbf1700):self.put(a,0)

    def state(self,settings):
        self.configure(**settings)
        category=self.call(0x20b180,ecx=s.TEAM)
        self.call(0x20b820,ecx=self.defense,edx=s.SOURCE+0x19000,args=(0,))
        cv,fv,pv,qv=struct.unpack('<4I',self.m.mem_read(s.SOURCE+0x19000,16))
        def index(ptr,base,size,count):
            if ptr==0:return None
            n,rem=divmod(ptr-s.BOOK-base,size)
            if rem or not 0<=n<count:raise s.ScoringError(f'selector returned out-of-book pointer {ptr:#x}')
            return n
        return dict(offense_category=category,
                    category=index(cv,ip.CATEGORY_BASE,16,len(self.book.categories)),
                    formation=index(fv,ip.FORMATION_BASE,ip.FORMATION_SIZE,len(self.book.formations)),
                    front=index(pv,ip.PLAY_BASE,96,len(self.book.plays)),
                    coverage=index(qv,ip.PLAY_BASE,96,len(self.book.plays)))


def scenarios():
    # Each policy branch consumes scalar world values. The release gate runs
    # all four resulting transform values for every play, independently.
    out=[dict(down=d,distance=n,yard=y) for d,n,y in itertools.product(range(1,5),(1,3,5,10,20,99),(1,5,20,50,80,95,99))]
    out += [dict(margin=m,quarter=q,seconds=t) for m,q,t in itertools.product((-26,-25,-15,-14,-4,-3,0,3,4,14,15,25,26),(1,2,3,4,5),(0,1,2,5,10,30,60,120,300))]
    # 0x20B400's phase dispatch accepts 1..4. Later phases have no
    # play-call category and are not legal calls to 0x20B820.
    out += [dict(phase=p) for p in (1,2,3)]
    out += [dict(direction=-1,down=d,yard=y) for d,y in itertools.product(range(1,5),(1,5,20,50,80,95,99))]
    return out


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--image',type=Path,required=True)
    ap.add_argument('--xbe',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--team');ap.add_argument('--limit',type=int);ap.add_argument('--compiled',type=Path)
    args=ap.parse_args();m=World(args.xbe.read_bytes());states=scenarios()[:args.limit]
    out=dict(status='PROVED OFFLINE',runtime_witness=False,states=states,fixture=__doc__,books=[])
    with OuterImage(args.image) as image:
        for team,entry in BOOK_ENTRIES.items():
            if args.team and team!=args.team:continue
            variants={'retail':image.read_entry(entry)}
            path=args.compiled/f'{team}.bin' if args.compiled else None
            if path and path.is_file():variants['authored']=path.read_bytes()
            for variant,raw in variants.items():
                m.load(raw);faults=[];choices=Counter();start=time.monotonic()
                for i,state in enumerate(states):
                    try:choices[tuple(m.state(state).items())]+=1
                    except s.ScoringError as e:faults.append(dict(state=i,input=state,error=str(e),detail=m.problem))
                # Every offensive formation: candidate iteration and both
                # transform branches in native 0x2096A0, all family filters.
                m.configure()
                for form in m.book.formations:
                    fv=s.BOOK+ip.FORMATION_BASE+form.index*ip.FORMATION_SIZE
                    code=(m.get(fv+4)>>8)&63
                    if code not in (0,1,2,3):continue
                    cv=m.call(0xe1a80,ecx=s.BOOK,edx=fv)
                    for kind in range(9):
                        for situation in (0,1):
                            try:m.call(0x2096a0,ecx=s.TEAM,edx=kind,args=(fv,cv,situation))
                            except s.ScoringError as e:faults.append(dict(formation=form.index,kind=kind,situation=situation,error=str(e),detail=m.problem))
                row=dict(book=team,variant=variant,resource_sha256=__import__('hashlib').sha256(raw).hexdigest(),
                         states=len(states),calls=dict(m.counts),visits=dict(m.visits),environment=dict(m.environment_calls),
                         choices=[dict(result=dict(k),count=v) for k,v in choices.items()],faults=faults,seconds=time.monotonic()-start)
                out['books'].append(row);args.output.write_text(json.dumps(out,indent=2)+'\n')
                print(team,variant,len(states),len(faults),round(row['seconds'],2),flush=True)
    return int(any(r['faults'] for r in out['books']))
if __name__=='__main__':sys.exit(main())
