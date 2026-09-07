"""Bounded retail x86 proofs, with native TXTR registration and material binding.

No console/game emulator. Heap, live objects and resource I/O completion are
explicit fixtures; lookup, relocation, post-binder seams and material stores
execute the retail instructions with actual section permissions.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_guardian_overlay as g
from mod_editor.core import nfl2k5_guardian_resources as art
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

EXTRACTION=Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION","/media/noah/Storage/for codex 1.0/extracted"))/"ESPN NFL 2K5 (USA)"
XBE, PACK = EXTRACTION/"default.xbe", EXTRACTION/"vc_53450030/B"
HAVE_UC=importlib.util.find_spec("unicorn") is not None


class Machine:
    HEAP, STACK, STOP = 0x4000000, 0x5000000, 0x5010000

    def __init__(self,payload):
        import unicorn as uc
        from unicorn import x86_const as x
        self.x=x;self.uc=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_32)
        image=XbeImage(payload);pages={}
        for s in image.sections:
            if not s.flags&2:continue
            for page in range(s.start&-4096,(s.end+4095)&-4096,4096):
                flags=uc.UC_PROT_READ|(uc.UC_PROT_EXEC if s.executable else 0)|(uc.UC_PROT_WRITE if s.writable else 0)
                pages[page]=pages.get(page,0)|flags
        for page in pages:self.uc.mem_map(page,4096)
        self.uc.mem_map(image.base,4096);self.uc.mem_write(image.base,payload[:image.headers_size])
        for s in image.sections:
            if s.flags&2:self.uc.mem_write(s.start,payload[s.raw:s.raw+s.raw_size])
        for page,flags in pages.items():self.uc.mem_protect(page,4096,flags)
        self.uc.mem_map(self.HEAP,0x200000);self.uc.mem_map(self.STACK,0x10000)
        self.uc.mem_map(self.STOP,4096,uc.UC_PROT_READ|uc.UC_PROT_EXEC)
        self.cursor=self.HEAP;self.writes=[];self.visits=[]
        self.context=self.alloc(128);self.put(0xb09578,self.context);self.put(0xb09590,0)
        self.render=self.alloc(84*2);self.record=self.alloc(84);self.entity=self.alloc(32)
        self.scene=self.alloc(64);self.material=self.alloc(64*128)
        self.frame=self.STACK+0xe000
        self.put(0xb652d0,self.render);self.put(0xb65274,2)
        self.put(self.render,self.record);self.put(self.render+0x2c,self.entity);self.put(self.entity,self.record)
        self.put(self.scene+0x1c,64);self.put(self.scene+0x20,self.material)
        self.put(self.render+0x14,self.scene);self.put(self.render+0x1c,self.scene)
        self.put(0xe5ff80,14)
        self.uc.hook_add(uc.UC_HOOK_MEM_WRITE,lambda _u,_a,addr,size,value,_d:self.writes.append((addr,size,value)))
        self.uc.hook_add(uc.UC_HOOK_CODE,lambda _u,addr,_s,_d:self.visits.append(addr))

    def alloc(self,n):
        at=(self.cursor+127)&-128;self.cursor=at+n;return at
    def put(self,va,value):self.uc.mem_write(va,struct.pack("<I",value&0xffffffff))
    def get(self,va):return struct.unpack("<I",self.uc.mem_read(va,4))[0]
    def string(self,s):
        data=(s+"\0").encode("utf-16le");at=self.alloc(len(data));self.uc.mem_write(at,data);return at
    def reg(self,name):return self.uc.reg_read(getattr(self.x,"UC_X86_REG_"+name.upper()))
    def run(self,entry,*,stop=None,args=(),limit=5000,**regs):
        stop=self.STOP if stop is None else stop
        sp=self.STACK+0xf000
        self.uc.mem_write(sp,struct.pack("<"+"I"*(len(args)+1),self.STOP,*args))
        self.uc.reg_write(self.x.UC_X86_REG_ESP,sp)
        for name,value in regs.items():self.uc.reg_write(getattr(self.x,"UC_X86_REG_"+name.upper()),value)
        self.writes.clear();self.visits.clear()
        self.uc.emu_start(entry,stop,count=limit)
        if self.reg("eip")!=stop:raise AssertionError(f"instruction bound at {self.reg('eip'):#x}")
        expected=sp if stop!=self.STOP else sp+4+4*len(args)
        if self.reg("esp")!=expected:raise AssertionError("stack imbalance")
    def load(self,span):
        tx=art.cap.models._tools_module("nfl_txtr");chunk=tx.parse_chunks(span)[0]
        body=tx.decode_chunk(span,chunk)[0];tex=tx.parse_texture(body,chunk)
        at=self.alloc(len(body));self.uc.mem_write(at,body);self.put(0xb120d8,at+chunk.system_bytes)
        self.run(0x43e30,args=(0x44dc0,),ecx=at,edx=0x44da0,limit=2000)
        descriptor=at+tex.descriptor_offset
        if self.get(descriptor+4)!=at+128 or self.get(descriptor+8)!=at+128+tex.palette_offset:
            raise AssertionError("native texture relocation differs")
        if self.get(at+0x14)!=descriptor:raise AssertionError("native descriptor registration differs")
        return descriptor
    def materials(self,lod=0):
        self.lod=lod;self.b=14 if lod==0 else 2
        self.uc.mem_write(0xb6531f+lod*62,bytes([self.b]))
        for i in range(64):
            at=self.material+i*128
            self.uc.mem_write(at,bytes(128));self.put(at,self.string("HI_HELMET_B" if i==self.b else f"other{i}"))
            self.put(at+8,0x12345601);self.put(at+0x30,0x11111111);self.put(at+0x34,0x22222222)
        return self.material+self.b*128
    def bind(self,flag=False,helmet=0,mode=14):
        self.uc.mem_write(self.record+0x53,bytes([0x1f|(0x20 if flag else 0)]))
        self.uc.mem_write(self.record+0xc,bytes([helmet<<6]));self.put(0xe5ff80,mode)
        self.put(self.frame+8,self.lod);self.put(self.frame-0x14,0x456789ab)
        self.run(0x8f02e,stop=0x8f033,eax=0x11223344,ecx=0x22334455,edx=0x33445566,
                 ebx=self.record,esi=self.render,edi=self.scene,ebp=self.frame,eflags=0x647)


@unittest.skipUnless(HAVE_UC and XBE.is_file() and PACK.is_file(),"Unicorn and retail USA XBE/helmet donor required")
class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=g.apply(XBE.read_bytes())[0]
        with PACK.open("rb") as f:
            donor=art.cap.TARGETS[2];f.seek(donor.pack_offset);template=f.read(donor.size)
        cls.texture=art.compile_texture(template)[0]

    def test_flags_both_helmets_both_lods_practice_and_missing_texture(self):
        for lod in (0,2):
            for helmet in (0,1):
                m=Machine(self.payload);texture=m.load(self.texture);b=m.materials(lod)
                for flag,mode in ((False,14),(True,14),(False,0),(False,1),(False,2),(False,3),(False,4),(False,0xffffffff)):
                    with self.subTest(lod=lod,helmet=helmet,flag=flag,mode=mode):
                        before=bytes(m.uc.mem_read(m.material,64*128))
                        m.bind(flag,helmet,mode)
                        enabled=flag or mode<=3
                        self.assertEqual(m.get(b+8)&1,int(not enabled))
                        self.assertEqual(m.get(b+0x30),texture if enabled else 0)
                        self.assertEqual(m.get(b+0x34),0);self.assertEqual(m.uc.mem_read(b+9,1),b"\0")
                        after=bytes(m.uc.mem_read(m.material,64*128))
                        self.assertEqual(before[:m.b*128],after[:m.b*128]);self.assertEqual(before[(m.b+1)*128:],after[(m.b+1)*128:])
                        self.assertEqual(m.reg("eax"),0x456789ab);self.assertEqual(m.reg("edx"),0x456789ab)
                        self.assertEqual(m.reg("ecx"),0x22334455);self.assertEqual(m.reg("eflags"),0x647)
                        self.assertEqual(m.reg("ebx"),m.record);self.assertEqual(m.reg("esi"),m.render);self.assertEqual(m.reg("edi"),m.scene)
                        self.assertFalse(any(m.record<=at<m.record+84 for at,_,_ in m.writes))
                        self.assertTrue(all(m.STACK<=at<m.STOP or b<=at<b+128 for at,_,_ in m.writes))
                # Simulate group release, then native re-registration: never reuse the old pointer.
                m.put(0xb09578,0);m.bind(True,helmet,14)
                self.assertEqual(m.get(b+0x30),0);self.assertEqual(m.get(b+8)&1,1)
                new_context=m.alloc(128);m.put(0xb09578,new_context)
                new_texture=m.load(self.texture);self.assertNotEqual(new_texture,texture)
                m.bind(True,helmet,14);self.assertEqual(m.get(b+0x30),new_texture)

    def test_practice_off_invalid_selector_headless_preview_and_stale_material(self):
        off=g.apply(XBE.read_bytes(),guardian_everyone_practice=False)[0]
        m=Machine(off);m.load(self.texture);b=m.materials()
        m.bind(False,0,1);self.assertEqual(m.get(b+8)&1,1)
        m.bind(True,0,1);self.assertEqual(m.get(b+8)&1,0)
        for helmet in (2,3):m.bind(True,helmet,1);self.assertEqual(m.get(b+8)&1,1)
        for at,val in ((m.render+4,1),(m.render+8,1),(m.render+0x2c,0),(0xb652d0,m.render+84),(0xb65274,0)):
            old=m.get(at);m.put(at,val);m.bind(True,0,1);self.assertEqual(m.get(b+8)&1,1);m.put(at,old)
        m.put(b,m.string("HI_HELMET_A"));before=bytes(m.uc.mem_read(m.material,64*128))
        m.bind(True,0,1);self.assertEqual(bytes(m.uc.mem_read(m.material,64*128)),before)

    def test_complete_retail_binder_retains_ac_facemasks_and_visors(self):
        for lod in (0,2):
            for helmet in (0,1):
                for visor in (0,1,2):
                    m=Machine(self.payload);m.load(self.texture);b=m.materials(lod)
                    uniform=m.alloc(32);m.put(uniform,0xff00ff00);m.put(0xb652b0,uniform)
                    indices=[255,12,13,14,15,16,17] if lod==0 else [255,0,1,2,3,21,22]
                    m.uc.mem_write(0xb6531c+lod*62,bytes([255])*62)
                    m.uc.mem_write(0xb6531c+lod*62,bytes(indices))
                    # Native facemask/visor route slots have their own materials.
                    image=XbeImage(self.payload)
                    for table,index in ((0x4ef3a8,40),(0x4ef3b0,41)):
                        slot=struct.unpack("<I",image.read(table+helmet*4,4))[0]
                        m.uc.mem_write(0xb6531c+lod*62+slot,bytes([index]))
                    m.uc.mem_write(0xb653d6+lod*27,b"\x2a")
                    m.run(0x8e9e0,args=(lod,helmet,0,visor,0,0,0),edi=m.scene,limit=2000)
                    chosen=indices[1 if helmet==0 else 5]
                    self.assertEqual(m.get(m.material+chosen*128+8)&1,0)
                    self.assertEqual(m.get(b+8)&1,1)
                    before=bytes(m.uc.mem_read(m.material,64*128))
                    m.bind(True,helmet,14)
                    self.assertEqual(m.get(b+8)&1,0)
                    after=bytes(m.uc.mem_read(m.material,64*128))
                    self.assertEqual(before[:m.b*128],after[:m.b*128]);self.assertEqual(before[(m.b+1)*128:],after[(m.b+1)*128:])

    def test_later_native_material_update_refreshes_cap_and_preserves_other_comparison(self):
        m=Machine(self.payload);texture=m.load(self.texture);b=m.materials(2);m.bind(True,1,14)
        m.put(m.frame+8,m.render)
        m.put(b+8,0x1234ff00);m.put(b+0x34,123)
        m.run(0x8fb45,stop=0x8fbb1,eax=m.b,ebx=124,edi=2,esi=b,ebp=m.frame,eflags=0x246)
        self.assertEqual(m.get(b+0x30),texture);self.assertEqual(m.get(b+0x34),0)
        self.assertEqual(m.uc.mem_read(b+9,1),b"\0")
        m.uc.mem_write(m.record+0x53,b"\x1f")
        m.run(0x8fb45,stop=0x8fbb1,eax=m.b,ebx=124,edi=2,esi=b,ebp=m.frame)
        self.assertEqual(m.get(b+8)&1,1);self.assertEqual(m.get(b+0x30),0)
        before=bytes(m.uc.mem_read(m.material,64*128))
        m.run(0x8fb45,stop=0x8fb4e,eax=21,ebx=124,edi=2,esi=m.material+21*128,ebp=m.frame)
        self.assertEqual(m.reg("ecx"),m.b);self.assertFalse(m.reg("eflags")&0x40)
        self.assertEqual(bytes(m.uc.mem_read(m.material,64*128)),before)

    def test_native_clone_carries_only_cap_and_replays_displaced_word(self):
        m=Machine(self.payload);source=m.record;dest=m.alloc(84)
        m.put(source+4,0xaabbccdd)
        for selected in (False,True):
            for existing in (0,0xff):
                m.uc.mem_write(source+0x53,bytes([0xdf|(0x20 if selected else 0)]))
                m.uc.mem_write(dest,bytes([existing])*84)
                before=bytes(m.uc.mem_read(dest,84))
                m.run(0xc16cd,stop=0xc16d5,ebp=source,edi=dest,eax=0xabcdef,ecx=0x12340000,eflags=0x647)
                result=bytes(m.uc.mem_read(dest,84));expected=bytearray(before)
                expected[4:6]=b"\xdd\xcc";expected[0x53]=(existing&~0x20)|(0x20 if selected else 0)
                self.assertEqual(result,expected);self.assertEqual(m.reg("ecx"),0x1234ccdd)
                self.assertEqual(m.reg("eax"),0xabcdef);self.assertEqual(m.reg("eflags"),0x647)

    def test_native_collection_reader_advances_into_appended_texture(self):
        m=Machine(self.payload)
        # Only asynchronous I/O completion and finished notification are stubs.
        m.uc.mem_write(0x48ff0,b"\xc2\x14\x00");m.uc.mem_write(0x43880,b"\xc3")
        m.put(0xb0957c,0);header=m.alloc(32);m.uc.mem_write(header,self.texture[:32])
        m.put(0xb0959c,0);m.put(0xb095a4,0);m.put(0xb095b0,32);m.put(0xb095b4,header);m.put(0xb095b8,0)
        start=art.RETAIL_START+art.RETAIL_SIZE;end=start+len(self.texture)
        m.put(0xb095a0,end);m.put(0xb09598,start)
        m.run(0x43a20,ecx=m.context,limit=200);self.assertIn(0x48ff0,m.visits)
        m.put(0xb09598,start+32)
        m.run(0x438d0,args=(m.context,),edx=0xb09598,limit=300)
        self.assertEqual(m.get(0xb09598),end);self.assertIn(0x43880,m.visits)

    def test_missing_cap_in_populated_resource_group(self):
        m=Machine(self.payload)
        unrelated=bytearray(self.texture)
        unrelated[64:82]="helmet00\0".encode("utf-16le")
        m.load(bytes(unrelated));b=m.materials()
        m.bind(True,1,14)
        self.assertEqual(m.get(b+8)&1,1)
        self.assertEqual(m.get(b+0x30),0)
        self.assertIn(0x449e0,m.visits);self.assertIn(0x443d0,m.visits)


if __name__=="__main__":unittest.main()
