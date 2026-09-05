"""Standalone bounded x86 proof. Native lookup/relocation runs; no console emulator."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scorebug_runtime as r
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
from mod_editor.core import nfl2k5_scorebug_resources as art
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

EXTRACTION = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)'
XBE, PACK = EXTRACTION / 'default.xbe', EXTRACTION / 'vc_53450030/0'
HAVE_UC = importlib.util.find_spec('unicorn') is not None
HAVE_CS = importlib.util.find_spec('capstone') is not None


def repin(buf):
    for s in _sections(buf):
        buf[s.header_offset+36:s.header_offset+56] = section_digest(buf,s)
    return bytes(buf)


class PublicTests(unittest.TestCase):
    def test_capacity_all_names_and_no_toolchain_dependency(self):
        requests = r.REQUESTS + kickoff.REQUESTS
        allocated = space._allocations(requests)
        self.assertLessEqual(max(a['va']+a['size'] for a in allocated if a['kind']=='code'), space.DATA_VA)
        for a in allocated:
            self.assertEqual(a['va'] % a['align'], 0)
        self.assertEqual(len(r.code_for(0x14baa60,0x14bb010)[0]),r.CODE_SIZE)
        names = [art.runtime_panel_name(code,side,n) for code in ['--'] + [a['asset_code'] for a in art.TEAM_LOGOS.values()] for side in ('home','away') for n in range(4)]
        self.assertEqual(len(set(names)),264)
        self.assertEqual(r.status(b'bad'), 'foreign')
        with self.assertRaises(ValueError): r.apply(b'bad')


@unittest.skipUnless(XBE.is_file(), 'pinned USA default.xbe evidence absent')
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.base = space.apply(cls.retail,r.REQUESTS+kickoff.REQUESTS)[0]
        cls.patched, cls.receipt = r.apply(cls.base)

    def test_both_orders_identical_stable_allocations_and_idempotence(self):
        first = kickoff.apply(self.patched)[0]
        second = r.apply(kickoff.apply(self.base)[0])[0]
        self.assertEqual(first, second)
        self.assertEqual(space.layout(first)['allocations'],space.layout(self.base)['allocations'])
        self.assertEqual(r.status(first),'applied')
        self.assertEqual(kickoff.status(first),'applied')
        self.assertEqual(r.apply(first)[0],first)
        self.assertEqual(r.apply(first)[1]['changed_bytes'],0)
        self.assertEqual(r.apply(self.retail)[1]['experimental'],True)
        self.assertFalse(self.receipt['runtime_witnessed'])
        for s in _sections(first): self.assertEqual(s.stored_digest,section_digest(first,s))
        with self.assertRaisesRegex(ValueError,'missing scorebug'):
            r.apply(kickoff.apply(self.retail)[0])

    def test_foreign_hook_code_data_guard_and_partial_install_refuse(self):
        code,data = r.sites(self.patched)
        for off in [code['raw'],data['raw']] + [r.scene.layout.sbpos.va_to_off(self.patched,va) for va,_ in r.HOOKS.values()]:
            bad=bytearray(self.patched);bad[off]^=1;before=bytes(bad)
            self.assertEqual(r.status(before),'foreign')
            with self.assertRaises(ValueError):r.apply(before)
            self.assertEqual(bytes(bad),before)
        # Correctly resealed code with retail hooks is still a partial install.
        bad=bytearray(self.patched)
        for va,original in r.HOOKS.values():
            off=r.scene.layout.sbpos.va_to_off(bad,va);bad[off:off+5]=original
        self.assertEqual(r.status(repin(bad)),'foreign')
        for guard in r.scene.XBE_GUARDS:
            bad=bytearray(self.retail);bad[r.scene.layout.sbpos.va_to_off(bad,guard[0])]^=1
            self.assertEqual(r.status(repin(bad)),'foreign')

    def test_recorded_owner_has_complete_hooks_and_zero_data_allocation(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder=Recorder(self.retail)
        recorder.observe(space,'apply',self.retail,self.base,{})
        recorder.observe(r,'apply',self.base,self.patched,self.receipt)
        spans=recorder.finish(self.patched)
        for va,original in r.HOOKS.values():
            self.assertTrue(any(row['owner']==r.OWNER and int(row['start'],0)==va
                                and row['size']==len(original) for row in spans))
        for site in r.sites(self.patched):
            self.assertTrue(any(row['owner']==r.OWNER and int(row['start'],0)==site['va']
                                and row['size']==site['size'] for row in spans))



class Machine:
    """Map actual section flags; heap and IO are explicit fixture inputs.

    Native 43E30 -> 43D20 -> 44DA0 -> 34DF0 registers and relocates TXTRs.
    Native 449E0/443D0/30C40 and FBC70 resolve all names and material slots.
    Only the unrelated native visibility callback is replaced in isolated
    frame tests; a separate test runs its actual visibility/ramp path.
    """
    HEAP, STACK, STOP = 0x4000000, 0x5000000, 0x5010000
    def __init__(self,payload):
        import unicorn as uc
        from unicorn import x86_const as x
        self.x=x;self.uc=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_32)
        image=XbeImage(payload);pages={}
        for s in image.sections:
            if not s.flags&2:continue
            for page in range(s.start&-4096,(s.end+4095)&-4096,4096):
                flags=uc.UC_PROT_READ | (uc.UC_PROT_EXEC if s.executable else 0) | (uc.UC_PROT_WRITE if s.writable else 0)
                pages[page]=pages.get(page,0)|flags
        for page in pages:self.uc.mem_map(page,4096)
        self.uc.mem_map(image.base,4096)
        self.uc.mem_write(image.base,payload[:image.headers_size])
        for s in image.sections:
            if s.flags&2:self.uc.mem_write(s.start,payload[s.raw:s.raw+s.raw_size])
        for page,flags in pages.items():self.uc.mem_protect(page,4096,flags)
        self.uc.mem_map(self.HEAP,0x400000)
        self.uc.mem_map(self.STACK,0x10000)
        self.uc.mem_map(self.STOP,4096,uc.UC_PROT_READ|uc.UC_PROT_EXEC)
        self.cursor=self.HEAP;self.textures={};self.code,self.data=r.sites(payload)
        self.state=self.data['va'];self.labels=r.code_for(self.code['va'],self.state)[1]
        self.context=self.alloc(128);self.put(0xb09578,self.context)
        self.put(0xb09590,0)
        self.scene=self.alloc(128);self.material=self.alloc(11*128)
        self.put(self.scene+0x1c,11);self.put(self.scene+0x20,self.material)
        self.mats={}
        for i,(_,_,name) in enumerate(r.scene.layout.SUBMESHES):
            mat=self.material+i*128;self.put(mat,self.string(name));self.mats[name]=mat
        self.put(0xa95528,self.scene);self.put(0xa95520,1)
        self.home=self.alloc(64);self.away=self.alloc(64)
        self.put(r.SCORE_POINTERS[0],self.home);self.put(r.SCORE_POINTERS[1],self.away)
        for p in (self.home,self.away):self.put(p+4,3)
        self.clock=self.alloc(64);self.put(0xe60294,self.clock);self.float(self.clock+16,12)
        self.play=self.alloc(512);self.put(0xe602ec,self.play);self.put(self.play+4,1)
        self.put(0xe60280,0xe5fc20);self.put(0xe602b4,4);self.put(0xa95a70,1);self.put(0xa95a00,1)
        self.uc.mem_write(0xfc9c0,b'\xc2\x04\x00')
        self.writes=[];self.visits=[]
        self.uc.hook_add(uc.UC_HOOK_MEM_WRITE,lambda _u,_a,addr,size,value,_d:self.writes.append((addr,size,value)))
        self.uc.hook_add(uc.UC_HOOK_CODE,lambda _u,addr,_s,_d:self.visits.append(addr))

    def alloc(self,size):
        at=(self.cursor+127)&-128;self.cursor=at+size;return at
    def put(self,va,value):self.uc.mem_write(va,struct.pack('<I',value&0xffffffff))
    def get(self,va):return struct.unpack('<I',self.uc.mem_read(va,4))[0]
    def float(self,va,value):self.uc.mem_write(va,struct.pack('<f',value))
    def getf(self,va):return struct.unpack('<f',self.uc.mem_read(va,4))[0]
    def string(self,s):
        d=(s+'\0').encode('utf-16le');va=self.alloc(len(d));self.uc.mem_write(va,d);return va
    def identity(self,home='37',away='20',kind=0):
        for va,code in ((r.HOME_CONTEXT,home),(r.AWAY_CONTEXT,away)):
            self.put(va+0x10c,self.string(code) if code is not None else 0);self.put(va+0x128,kind)
    def run(self,va,args=(),limit=200000,**regs):
        x=self.x;sp=self.STACK+0xf000
        self.uc.mem_write(sp,struct.pack('<'+'I'*(len(args)+1),self.STOP,*args))
        self.uc.reg_write(x.UC_X86_REG_ESP,sp)
        for name,value in regs.items():self.uc.reg_write(getattr(x,'UC_X86_REG_'+name.upper()),value)
        self.visits.clear();self.writes.clear()
        self.uc.emu_start(va,self.STOP,count=limit)
        if self.uc.reg_read(x.UC_X86_REG_EIP)!=self.STOP:raise AssertionError('instruction bound exceeded')
        if self.uc.reg_read(x.UC_X86_REG_ESP)!=sp+4+len(args)*4:raise AssertionError('stack imbalance')
    def load(self,span):
        chunk,body,_=r.scene.decode(span);tex=r.scene.tx.parse_texture(body,chunk)
        at=self.alloc(len(body));self.uc.mem_write(at,body)
        self.put(0xb120d8,at+chunk.system_bytes)
        self.run(0x43e30,(0x44dc0,),ecx=at,edx=0x44da0,limit=1000)
        descriptor=at+tex.descriptor_offset
        if self.get(descriptor+4)!=at+chunk.system_bytes:raise AssertionError('native pixel relocation failed')
        if self.get(descriptor+8)!=at+chunk.system_bytes+4096:raise AssertionError('native palette relocation failed')
        if self.get(at+0x14)!=descriptor:raise AssertionError('native object relocation failed')
        self.textures[tex.name]=descriptor
    def setup(self):self.run(self.labels['setup'])
    def update(self,dt=1/60):self.run(self.labels['update'],(struct.unpack('<I',struct.pack('<f',dt))[0],))


@unittest.skipUnless(XBE.is_file() and PACK.is_file() and HAVE_UC,'retail XBE/pack 0 and Unicorn required for bounded native execution')
class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=kickoff.apply(r.apply(space.apply(XBE.read_bytes(),r.REQUESTS+kickoff.REQUESTS)[0])[0])[0]
        with PACK.open('rb') as stream:
            record=art.RESOURCES['score_buga'];stream.seek(record['pack_offset']);cls.template=stream.read(record['span_size'])
        # Native descriptor, pixels and names are real compiler output; single
        # neutral source pixels suffice for ABI tests across all texture names.
        cls.panel=next(art.panel_states(b'',None,'away'))
        cls.spans=[art.runtime_panel(cls.template,cls.panel,art.runtime_panel_name(code,side,count))
                   for code in ['--']+[v['asset_code'] for v in art.TEAM_LOGOS.values()]
                   for side in ('home','away') for count in range(4)]
    def machine(self):
        m=Machine(self.payload)
        for span in self.spans:m.load(span)
        m.identity();m.setup();return m
    def test_native_loading_binding_fallback_and_next_game(self):
        m=self.machine()
        for team in art.TEAM_LOGOS.values():
            code=team['asset_code'];m.identity(code,code);m.setup()
            self.assertEqual(m.get(m.mats['hscore_buga']+0x30),m.textures[f'sb{code}h3'])
            self.assertEqual(m.get(m.mats['zscore_buga']+0x30),m.textures[f'sb{code}a3'])
        m.identity();m.setup();m.update()
        for mat,name in [('hscore_buga','sb37h3'),('zscore_buga','sb20a3')]:
            self.assertEqual(m.get(m.mats[mat]+0x30),m.textures[name]);self.assertFalse(m.get(m.mats[mat]+8)&1)
        self.assertEqual(m.get(0xa95b00),0)
        for home,away,kind in [('18','14',0),('02','22',0),('99',None,0),('20','37',2),('20','37',4),('20X','0/',0)]:
            m.identity(home,away,kind);m.setup();m.update()
            for side,code,mat in [('home',home,'hscore_buga'),('away',away,'zscore_buga')]:
                valid=code in ('18','14','02','22') and kind==0
                name=art.runtime_panel_name(code if valid else '--',side,3)
                self.assertEqual(m.get(m.mats[mat]+0x30),m.textures[name])
            self.assertEqual(m.get(r.SCORE_COLORS[0]),r.WHITE)
        # A recognized but missing logo retries the neutral texture.
        m.identity('00','01')
        # Remove the named home texture object from lookup by renaming its name.
        descriptor=m.textures['sb00h3'];m.uc.mem_write(descriptor-24,b'X\0')
        m.setup();m.update()
        self.assertEqual(m.get(m.mats['hscore_buga']+0x30),m.textures['sb--h3'])
    def test_timeout_counts_independent_reset_and_invalid(self):
        m=self.machine()
        for home in (3,2,1,0,3,2,0xffffffff,4):
            for away in (3,2,1,0):
                m.put(m.home+4,home);m.put(m.away+4,away);m.update()
                self.assertEqual(m.get(m.mats['hscore_buga']+0x30),m.textures[f'sb37h{home if home<=3 else 0}'])
                self.assertEqual(m.get(m.mats['zscore_buga']+0x30),m.textures[f'sb20a{away}'])
    def test_score_flash_first_population_change_expiry_and_scene_reset(self):
        m=self.machine();m.put(m.home,7);m.update()
        self.assertEqual(m.get(r.SCORE_COLORS[0]),r.WHITE)
        m.put(m.home,10);m.update()
        self.assertEqual(m.get(r.SCORE_COLORS[0]),r.ACCENT);self.assertEqual(m.get(r.SCORE_COLORS[1]),r.WHITE)
        for _ in range(12):m.update()
        self.assertEqual(m.get(r.SCORE_COLORS[0]),r.WHITE)
        m.put(m.away,2);m.update();self.assertEqual(m.get(r.SCORE_COLORS[1]),r.ACCENT)
        m.setup();m.update();self.assertEqual(m.get(r.SCORE_COLORS[1]),r.WHITE)
    def test_down_distance_possession_refresh_only_on_changes(self):
        m=self.machine();m.float(0xa95a04,30);m.update()
        self.assertEqual(m.getf(0xa95a04),30)
        for va,value in [(m.play+4,2),(m.play+0x18,123),(m.play+0x28,234),(0xe60280,0xe5fc60)]:
            m.put(va,value);m.update();self.assertEqual(m.getf(0xa95a04),1)
            m.float(0xa95a04,30);m.update();self.assertEqual(m.getf(0xa95a04),30)
        m.put(0xa95a00,0);m.put(m.play+4,3);m.update();self.assertEqual(m.getf(0xa95a04),30)
    def test_clock_boundaries_disabled_nan_negative_and_resume(self):
        m=self.machine()
        for seconds in (6,5,4.9,4,1,0,-1,float('inf'),float('nan')):
            for flags,visible in ((0,1),(2,1),(4,1),(0,0)):
                m.float(m.clock+16,seconds);m.put(m.clock+24,flags);m.put(0xa95a70,visible);m.update()
                urgent=0<=seconds<5 and flags==0 and visible==1
                self.assertEqual(m.get(0xa95a48),r.RED if urgent else r.DARK)
    def test_native_collection_reader_uses_grown_end_and_wrapper_sizes(self):
        m=Machine(self.payload)
        # IO completion and collection-finished notification are host boundaries.
        # Execute both native header dispatch and end checks, including the old
        # retail end, all appended wrappers, and the new exact end.
        m.uc.mem_write(0x48ff0,b'\xc2\x14\x00')
        m.uc.mem_write(0x43880,b'\xc3')
        m.put(0xb0957c,0)  # resource-handler work proved independently by load()
        header=m.alloc(32);m.uc.mem_write(header,self.spans[0][:32])
        m.put(0xb0959c,0);m.put(0xb095a4,0);m.put(0xb095b0,32)
        m.put(0xb095b4,header);m.put(0xb095b8,0)
        start=art.HUD_START+art.HUD_SIZE;end=start+art.RUNTIME_APPEND_SIZE
        m.put(0xb095a0,end)
        m.put(0xb09598,start)
        m.run(0x43a20,ecx=m.context,limit=200)
        self.assertIn(0x48ff0,m.visits)  # old retail end is no longer EOF
        for i in range(art.RUNTIME_TEXTURE_COUNT):
            m.put(0xb09598,start+i*art.RUNTIME_TEXTURE_SPAN+32)
            m.run(0x438d0,(m.context,),edx=0xb09598,limit=250)
            self.assertEqual(m.get(0xb09598),start+(i+1)*art.RUNTIME_TEXTURE_SPAN)
            self.assertIn(0x48ff0 if i+1<art.RUNTIME_TEXTURE_COUNT else 0x43880,m.visits)
        self.assertNotIn(0x48ff0,m.visits)

    def test_native_visibility_and_slide_driver_after_new_down(self):
        m=self.machine();m.update()
        m.put(m.play+4,2);m.update();self.assertEqual(m.getf(0xa95a04),1)
        image=XbeImage(self.payload)
        # Restore the actual native visibility writer. Stub only external scene
        # predicates/field math, all explicitly unrelated to the down ramp.
        m.uc.mem_write(0xfc9c0,image.read(0xfc9c0,780));m.uc.ctl_remove_cache(0xfc9c0,0xfcccc)
        for va in (0xabe90,0x72190,0xa7940):m.uc.mem_write(va,b'\x31\xc0\xc3')
        for va in (0xfbcc0,0xa6300):m.uc.mem_write(va,b'\xd9\xee\xc3')
        m.uc.mem_write(0xfc700,b'\xc3')
        m.put(0xe5fc20+0xc,0xfffffffc);m.put(0xe602b8,12);m.put(0xe602fc,0)
        m.put(0xa95b54,0);m.put(0xa95b44,0);m.put(0xa95c34,0);m.put(0xa95c24,0)
        for i in range(6):m.put(0xa95a20+i*0x70,int(i==0))
        m.put(0xa95a0c,m.mats['dscore_buga']);m.put(0xa95a00,1)
        positions=[]
        for _ in range(12):
            sp=m.STACK+0xf000;m.uc.mem_write(sp,struct.pack('<II',m.STOP,0x3c888889))
            m.uc.reg_write(m.x.UC_X86_REG_ESP,sp)
            m.uc.emu_start(0xfce70,0xfcfa7,count=10000)
            self.assertEqual(m.uc.reg_read(m.x.UC_X86_REG_EIP),0xfcfa7)
            positions.append(m.getf(0xa95a04));self.assertEqual(m.get(0xa95a00),1)
        self.assertAlmostEqual(positions[0],3.5,places=5)
        self.assertEqual(positions[-1],30)
        self.assertEqual(positions,sorted(positions))
        self.assertFalse(m.get(m.mats['dscore_buga']+8)&1)

    def test_register_flags_x87_sse_and_owned_writes(self):
        m=self.machine();x=m.x
        # Native call stubs make its side effects explicit; compare our hook's
        # preservation against that continuation state, including nonempty x87.
        m.uc.mem_write(0xfc1a0,b'\xc3')
        m.uc.ctl_remove_cache(0xfc1a0,0xfc1f9)
        values={n:0x13570000+i for i,n in enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP'))}
        for hook,args in [('setup',()),('update',(0x3c888889,))]:
            for n,v in values.items():m.uc.reg_write(getattr(x,'UC_X86_REG_'+n),v)
            m.uc.reg_write(x.UC_X86_REG_EFLAGS,0x646)
            m.uc.reg_write(x.UC_X86_REG_FPCW,0x37f);m.uc.reg_write(x.UC_X86_REG_FPSW,0)
            for i in range(8):m.uc.reg_write(getattr(x,f'UC_X86_REG_FP{i}'),(0x8000000000000000+i,0x3fff))
            m.uc.reg_write(x.UC_X86_REG_FPTAG,0)
            for i in range(8):m.uc.reg_write(getattr(x,f'UC_X86_REG_XMM{i}'),(i+1)*0x123456789abcdef0123456789abcdef)
            regs=[getattr(x,'UC_X86_REG_'+n) for n in values]+[x.UC_X86_REG_EFLAGS,x.UC_X86_REG_FPCW,x.UC_X86_REG_FPSW,x.UC_X86_REG_FPTAG]+[getattr(x,f'UC_X86_REG_XMM{i}') for i in range(8)]+[getattr(x,f'UC_X86_REG_FP{i}') for i in range(8)]+[x.UC_X86_REG_MXCSR]
            before=[m.uc.reg_read(n) for n in regs]
            m.run(m.labels[hook],args)
            self.assertEqual([m.uc.reg_read(n) for n in regs],before)
            for va,size,_ in m.writes:
                self.assertFalse(space.CODE_VA<=va<space.DATA_VA)
                if space.DATA_VA<=va<space.DATA_VA+space.PAGE:
                    self.assertTrue(m.state<=va and va+size<=m.state+r.DATA_SIZE)
                self.assertFalse(0x11000<=va<0x4e0000)
            self.assertIn(0xfc1a0 if hook=='setup' else 0xfc9c0,m.visits)


if __name__=='__main__':unittest.main()
