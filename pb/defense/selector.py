#!/usr/bin/env python3
"""PROVED OFFLINE: retail selector under explicit synthetic matchup inputs.
DESIGN: actor matchup and formation scores are fixture inputs; no live rate claim.
"""
import hashlib
from pathlib import Path
import random
import struct
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from tests.nfl2k5_play_menu_walk_native import MenuWalker,BOOK_VA,STACK,STOP
from mod_editor.core import nfl2k5_playbook_inspector as ip
XBE=Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')
XBE_SHA='73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9'
TEAM=0xe5fc20; LIVE=0x2401000; STATE=0x2400400; DIR=0x2400800; OUTPUT=0x2400c00

class Selector(MenuWalker):
    def __init__(self,xbe,resource,seed=924):
        assert hashlib.sha256(xbe).hexdigest()==XBE_SHA
        super().__init__(xbe,resource)
        # MenuWalker maps file-backed sections only; selector uses the BSS globals too.
        regions=list(self.uc.mem_regions());top=max(b+1 for a,b,_ in regions if a<BOOK_VA)
        if top<0xf00000:self.uc.mem_map(top,0xf00000-top)
        self.put(0xbe4e20,0x521078) # PROVED OFFLINE: retail startup opcode table.
        self.stub_calls={}
        self.book=ip.parse_playbook_resource(resource)
        self.codes={c.index:resource[32+ip.CATEGORY_BASE+16*c.index+4]&63 for c in self.book.categories}
        self.put(TEAM+0x20,BOOK_VA);self.put(TEAM+0xc,LIVE);self.put(TEAM+8,DIR)
        self.put(DIR+0xc,DIR+0x100);self.fput(DIR+0x104,1)
        self.put(0xe60280,TEAM);self.put(0xe602ec,STATE)
        assert bytes(self.uc.mem_read(0xbf1168,54*4))==bytes(54*4)
        assert bytes(self.uc.mem_read(0xc5d508,4))==bytes(4)
        # PROVED OFFLINE: relocate play names/chains, then execute retail validation.
        # Category/formation header pointers were relocated by MenuWalker.
        for p in self.book.plays:
            base=ip.PLAY_BASE+p.index*96
            for offset in (base,*(base+12+8*s for s in range(11))):
                value=struct.unpack_from('<i',resource,32+offset)[0]
                if value:self.put(BOOK_VA+offset,BOOK_VA+offset+value-1)
            error=self.call(0x1a9840,ecx=BOOK_VA+base)
            if error:raise ValueError(f'Native validator rejected {p.index} {p.name}: {error:x}')
            self.call(0x1a9a80,ecx=BOOK_VA+base)
        self.native_validated=len(self.book.plays)
        rng=random.Random(seed);self.put(0xe5fca0,0);self.put(0xe5fca4,31)
        self.uc.mem_write(0xe5fca8,b''.join(struct.pack('<Q',rng.getrandbits(64)) for _ in range(55)))
        self.matchup=.5;self.prevent=False;self.category=0
        self.stub_calls={}
        self.stubs={0x205660:lambda:self.freturn(self.matchup,12),
                    0x207ef0:lambda:self.freturn(1,8),
                    0x20b400:lambda:self._return(self.category),
                    0x1889c0:lambda:self._return(0),
                    0x2045f0:lambda:self._return(0),
                    0x204ab0:lambda:self._return(0),
                    0x208420:lambda:self._return(int(self.prevent))}
        for addr in self.stubs:self.uc.hook_add(self.u.UC_HOOK_CODE,self.fixture_hook,begin=addr,end=addr)
        for pop in (8,12):
            self.uc.mem_write(STOP+0x100+pop*16,b'\xd9\x05'+struct.pack('<I',STOP+0x80)+b'\xc2'+struct.pack('<H',pop))
    def put(self,va,value):self.uc.mem_write(va,struct.pack('<I',value))
    def fput(self,va,value):self.uc.mem_write(va,struct.pack('<f',value))
    def freturn(self,value,pop):
        self.fput(STOP+0x80,value)
        self.uc.reg_write(self.r.UC_X86_REG_EIP,STOP+0x100+pop*16)
    def fixture_hook(self,uc,address,size,data):
        self.stub_calls[hex(address)]=self.stub_calls.get(hex(address),0)+1
        self.stubs[address]()
    def call(self,addr,ecx=0,edx=0,args=(),ebx=0,esi=0,edi=0):
        r=self.r
        self.uc.mem_write(STACK,struct.pack('<I',STOP)+b''.join(struct.pack('<I',a) for a in args))
        for reg,value in ((r.UC_X86_REG_ESP,STACK),(r.UC_X86_REG_EAX,0),(r.UC_X86_REG_ECX,ecx),(r.UC_X86_REG_EDX,edx),(r.UC_X86_REG_EBX,ebx),(r.UC_X86_REG_ESI,esi),(r.UC_X86_REG_EDI,edi),(r.UC_X86_REG_EBP,0)):
            self.uc.reg_write(reg,value)
        try:self.uc.emu_start(addr,STOP,count=20000000)
        except Exception as e:
            raise RuntimeError(f'Native at {self.uc.reg_read(r.UC_X86_REG_EIP):x}; esp {self.uc.reg_read(r.UC_X86_REG_ESP):x}; esi {self.uc.reg_read(r.UC_X86_REG_ESI):x}; ebp {self.uc.reg_read(r.UC_X86_REG_EBP):x}; {self.stub_calls}') from e
        if self.uc.reg_read(r.UC_X86_REG_EIP)!=STOP:raise RuntimeError(f'Native selector did not return: {addr:x}, pc={self.uc.reg_read(r.UC_X86_REG_EIP):x}, ecx={self.uc.reg_read(r.UC_X86_REG_ECX):x}, edx={self.uc.reg_read(r.UC_X86_REG_EDX):x}, stack={bytes(self.uc.mem_read(self.uc.reg_read(r.UC_X86_REG_ESP),40)).hex()}, stubs={self.stub_calls}')
        return self.uc.reg_read(r.UC_X86_REG_EAX)
    def requested_category(self,offense_code,yardline,down,prevent=False):
        self.put(STATE+4,down);self.fput(STATE+0x18,4572-yardline*91.44)
        self.prevent=prevent
        return self.call(0x208480,edx=offense_code)
    def select(self,offense_code=6,yardline=50,down=1,distance=10,prevent=False,matchup=.5):
        self.matchup=matchup
        requested=self.requested_category(offense_code,yardline,down,prevent)
        # DESIGN: exact-code category fixture, falling back to nearest eligible code as in 0x2093F0.
        cats=[c for c in self.book.categories if requested<=self.codes[c.index]<=16]
        if not cats:raise ValueError(f'No defensive category {requested}')
        cat=min(cats,key=lambda c:(self.codes[c.index]-requested,c.index));self.category=BOOK_VA+ip.CATEGORY_BASE+cat.index*16
        self.call(0x20b820,ecx=TEAM,edx=OUTPUT,args=(0,))
        cv,fv,pv,qv=struct.unpack('<4I',self.uc.mem_read(OUTPUT,16))
        return dict(requested_code=requested,category_code=self.codes[cat.index],formation=(fv-BOOK_VA-ip.FORMATION_BASE)//ip.FORMATION_SIZE,
                    front=self.play_index(pv),coverage=self.play_index(qv),down=down,distance=distance,yardline=yardline,
                    matchup=matchup,prevent_fixture=prevent)

# PROVED OFFLINE: candidate arrays are read just before retail 0x203440.
# The model caches only state-invariant candidates under the disclosed fixtures.
def install_capture(s):
    s.candidates={}
    def capture(u,a,n,d):
        sp=u.reg_read(s.r.UC_X86_REG_ESP)
        kind,countreg,pbase,sbase=(('front','ESI',0x14,0x8c) if a==0x20aa1e else
                                  ('coverage','ESI',0x10,0x88) if a==0x20ac4d else
                                  ('formation','EBP',0x10,0x88))
        count=u.reg_read(getattr(s.r,'UC_X86_REG_'+countreg))
        assert 0<count<30,(kind,count) # Do not approximate native overflow behavior.
        pointers=struct.unpack('<'+str(count)+'I',u.mem_read(sp+pbase,count*4))
        scores=struct.unpack('<'+str(count)+'f',u.mem_read(sp+sbase,count*4))
        s.candidates[kind]=[dict(pointer=p,score=v) for p,v in zip(pointers,scores)]
    for a in (0x20aa1e,0x20ac4d,0x2083fe):s.uc.hook_add(s.u.UC_HOOK_CODE,capture,begin=a,end=a)

def probabilities(rows,power):
    # PROVED OFFLINE: rounded float32 powers as 0x203440 stores them.
    f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
    weights=[f32(r['score']**power) for r in rows]
    assert all(w>=0 for w in weights)
    total=sum(weights)
    return [w/total if total else 1/len(rows) for w in weights]

def native_weight_choice(s,rows,power):
    # Execute the original weighted lottery and its RNG; restore scores each call.
    s.uc.mem_write(STOP+0x500,struct.pack('<'+str(len(rows))+'f',*(r['score'] for r in rows)))
    index=s.call(0x203440,args=(STOP+0x500,len(rows),power))
    assert index<len(rows)
    return rows[index]['pointer']

def distribution(s,offense_code=6,yardline=50,down=1,prevent=False,matchup=.5):
    """PROVED OFFLINE: enumerate all legal pairs with native filtering and scoring.
    DESIGN: fixture inputs hold formation and player matchup scores fixed.
    """
    if not hasattr(s,'candidates'):install_capture(s)
    witness=s.select(offense_code,yardline,down,prevent=prevent,matchup=matchup)
    formation_rows=s.candidates['formation']; result=[]
    for fr,fp in zip(formation_rows,probabilities(formation_rows,1)):
        fv=fr['pointer'];s.call(0x20a7f0,args=(TEAM,s.category,fv))
        front_rows=s.candidates['front']
        for pr,pp in zip(front_rows,probabilities(front_rows,3)):
            s.call(0x20aa40,ebx=TEAM,args=(pr['pointer'],fv,s.category))
            coverage_rows=s.candidates['coverage']
            for cr,cp in zip(coverage_rows,probabilities(coverage_rows,3)):
                result.append(dict(formation=(fv-BOOK_VA-ip.FORMATION_BASE)//ip.FORMATION_SIZE,
                    front=s.play_index(pr['pointer']),coverage=s.play_index(cr['pointer']),
                    probability=fp*pp*cp,front_score=pr['score'],coverage_score=cr['score']))
    assert abs(sum(r['probability'] for r in result)-1)<1e-6
    assert any(all(witness[k]==r[k] for k in ('formation','front','coverage')) for r in result)
    return dict(status='PROVED OFFLINE',fixture=witness,pairs=result)
