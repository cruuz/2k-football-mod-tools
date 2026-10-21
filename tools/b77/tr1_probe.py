#!/usr/bin/env python3
"""Execute real rating getters on an XBE and unrelocated ROST body (no mocked leaves)."""
from __future__ import annotations
import argparse,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.nfl2k5_supersim_draft_fixture import Machine
from mod_editor.core import nfl2k5_roster_records as rr

def caller_census(payload):
    """Full-image rel32 CALL/JMP scan plus absolute references to native getters.

    Candidate instructions are individually decoded in the retained audit.
    The expected image has no absolute pointers to these three native getters.
    """
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    targets={0xC4830,0xC4860,0xC48A0};calls=[];pointers=[]
    for section in XbeImage(payload).sections:
        data=XbeImage(payload).read(section.start,section.raw_size)
        for i,op in enumerate(data[:-4]):
            if op in (0xE8,0xE9):
                dest=section.start+i+5+struct.unpack_from('<i',data,i+1)[0]
                if dest in targets:
                    calls.append(dict(site=section.start+i,target=dest,opcode=op))
        for target in targets:
            at=0;needle=struct.pack('<I',target)
            while (at:=data.find(needle,at))>=0:
                pointers.append(dict(site=section.start+at,target=target));at+=1
    return dict(calls=sorted(calls,key=lambda r:r['site']),absolute_references=pointers)


class Ratings(Machine):
    def __init__(self,xbe,body):
        super().__init__(xbe,trace_writes=False)
        self.doc=rr.RosterDocument(body,base=0,source='native proof')
        self.uc.mem_write(self.ARENA+0x300,body)
        self.fixup_roster(self.ARENA+0x340)
        self.stub=self.STOP+0x100
        self.output=self.ARENA+0x1f0020
        self.uc.mem_write(self.stub,b'\x8b\x0d'+struct.pack('<I',self.output+4)
                         +b'\xff\x15'+struct.pack('<I',self.output+8)
                         +b'\xd9\x1d'+struct.pack('<I',self.output)+b'\xc3')
    def rating(self,fn,team):
        self.put(self.output+4,team);self.put(self.output+8,fn)
        self.call(self.stub,budget=3000000)
        return self.f32(self.output)*100
    def team(self,i): return self.get(0xE5786C+4*i)
    def player(self,team,pos,n=0): return self.call(0xC3D30,ecx=team,edx=n,args=(pos,))
    def pool(self,team,pos,threshold=1):
        # Separate stable trampoline with arguments loaded from RAM, so no stale JIT blocks.
        at=self.STOP+0x200;args=self.output+32
        self.uc.mem_write(at,b'\x68\x00\x00\x80\x3f\x6a\x00'
            +b'\xff\x35'+struct.pack('<I',args+4)+b'\x68\xcd\xcc\xcc\x3d\x68\x80\x6d\x24\x00'
            +b'\xff\x35'+struct.pack('<I',args)+b'\xa1'+struct.pack('<I',args+8)
            +b'\xff\x15'+struct.pack('<I',args+12)+b'\xd9\x1d'+struct.pack('<I',self.output)+b'\xc3')
        for i,v in enumerate((team,threshold,pos,0xC4400)):self.put(args+4*i,v)
        self.call(at,budget=3000000);return self.f32(self.output)*100
    def rows(self, functions=None):
        functions=functions or (0xC4830,0xC4860,0xC48A0)
        out=[]
        for i,t in enumerate(self.doc.teams[:32]):
            team=self.team(i)
            out.append(dict(team=t.abbreviation,ratings=[self.rating(fn,team) for fn in functions],
                            fb_count=self.call(0xC3CB0,ecx=team,edx=8)))
        return out

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--xbe',type=Path,required=True);ap.add_argument('--body',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--display',action='store_true');a=ap.parse_args()
    payload=a.xbe.read_bytes();m=Ratings(payload,a.body.read_bytes())
    from mod_editor.core import nfl2k5_team_ratings as tr
    rows=m.rows(tr.entrypoints(payload) if a.display else None)
    a.out.write_text(json.dumps(dict(mocked_leaves=m.leaves,teams=rows),indent=2)+'\n',newline='\n')
    for r in rows:print(r['team'],*(f'{v:.2f}' for v in r['ratings']),f"FB={r['fb_count']}")
if __name__=='__main__':main()
