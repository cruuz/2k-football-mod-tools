"""Read-only allocator ownership and bounded native 200-item jukebox proof."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_music_metadata as music
from mod_editor.core import nfl2k5_music_storage as storage
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage,ReservationManifest,DEFAULT_MANIFEST
from mod_editor.core.nfl2k5_bump_strength import _sections,section_digest

XBE=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)/default.xbe'


def records(n=200):
    return [dict(title=f'Tone {i+1:03}',artist='Synthetic',frames=64*(i+1)) for i in range(n)]


class PortableMetadataTests(unittest.TestCase):
    def test_counts_identity_stability_and_allocation_budget(self):
        retail=music.identities(59)
        for n in (1,7,59,200,400):
            ids=music.identities(n)
            self.assertEqual(ids[:59],retail[:n])
            self.assertEqual(len(set(ids)),n)
            self.assertTrue(all(c<18 and s<256 for c,s in ids))
            data,fields=music.build(records(n))
            self.assertLessEqual(len(data),storage.CAPACITY-storage.PREFIX)
            self.assertEqual(sum(n for n,_ in fields),n)
        for n in (0,401):
            with self.assertRaises(ValueError): music.build(records(n))
        long=[dict(title='t'*120,artist='a'*120,frames=64) for _ in range(400)]
        with self.assertRaisesRegex(ValueError,'budget'): music.build(long)


@unittest.skipUnless(XBE.is_file(),'retail USA default.xbe evidence absent')
class RetailMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=XBE.read_bytes()
        cls.patched,cls.receipt=music.apply(cls.retail,records())

    def test_owned_read_only_records_exact_fields_digests_and_idempotence(self):
        self.assertEqual(music.status(self.retail),'retail')
        self.assertEqual(music.status(self.patched),'applied')
        self.assertEqual(music.apply(self.patched,records())[0],self.patched)
        image=XbeImage(self.patched)
        section=image.section(storage.VA)
        self.assertFalse(section.writable)
        self.assertFalse(section.executable)
        self.assertFalse(image.runtime_writable(storage.VA,storage.CAPACITY))
        self.assertEqual(music.songs(self.patched),records())
        for s in _sections(self.patched): self.assertEqual(s.stored_digest,section_digest(self.patched,s))
        for c in range(18):
            off=music._offset(self.retail,music.COLLECTIONS+c*32,24)
            self.assertEqual(self.retail[off:off+24],self.patched[off:off+24])
        text=image.section(0x11000)
        self.assertEqual(self.retail[text.raw:text.raw+text.raw_size],self.patched[text.raw:text.raw+text.raw_size])

    def test_mixed_foreign_corruption_and_different_recipe_refuse(self):
        for offset in (storage.RAW,storage.RAW+12,storage.RAW+storage.PREFIX+100,
                       storage.RAW+storage.CAPACITY-1,storage.HEADER,storage.REFS+4,
                       music._offset(self.patched,music.COLLECTIONS+24,8),
                       music._offset(self.patched,music.COLLECTIONS+8,12)):
            buf=bytearray(self.patched);buf[offset]^=1
            self.assertEqual(music.status(bytes(buf)),'foreign')
            with self.assertRaises(ValueError): music.apply(bytes(buf),records())
        with self.assertRaises(ValueError): music.apply(self.patched,records(199))

    def test_composes_with_special_and_relocated_code_in_both_orders(self):
        from mod_editor.core import nfl2k5_depth_chart_rows as rows,nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        from mod_editor.core import nfl2k5_modern_positions as modern
        payload,_=modern.apply(self.retail)
        payload,_=pools.apply(payload);payload,_=rows.apply(payload)
        payload,_=space.apply(payload,relocated.REQUESTS)
        first,_=relocated.apply(payload);first,_=music.apply(first,records())
        second,_=music.apply(payload,records());second,_=relocated.apply(second)
        self.assertEqual(first,second)
        self.assertEqual(rows.status(first),'applied')
        self.assertEqual(space.status(first),'applied')

    def test_fresh_mapping_ownership_and_raw_encoding_candidates_are_honest(self):
        manifest=ReservationManifest.load(DEFAULT_MANIFEST,XbeImage(self.retail))
        evidence=storage.allocation_evidence(self.retail,manifest)
        self.assertEqual(evidence['retail_mapping_overlaps'],[])
        self.assertEqual(evidence['manifest_overlaps'],[])
        self.assertTrue(evidence['raw_encoding_candidates'])
        if os.environ.get('NFL2K5_MUSIC_EVIDENCE_DIR'):
            (Path(os.environ['NFL2K5_MUSIC_EVIDENCE_DIR'])/'music-allocation.json').write_text(json.dumps(evidence,indent=2)+'\n')

    @unittest.skipUnless(importlib.util.find_spec('unicorn'),'Unicorn absent; bounded native jukebox probe unavailable')
    def test_native_200_node_build_save_scroll_and_metadata_consumers(self):
        from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE,UC_PROT_READ
        from unicorn.x86_const import (UC_X86_REG_EIP,UC_X86_REG_ESP,UC_X86_REG_EAX,
                                      UC_X86_REG_ECX,UC_X86_REG_EDX,UC_X86_REG_EBP)
        uc=Uc(UC_ARCH_X86,UC_MODE_32)
        uc.mem_map(0x10000,0x1600000)
        uc.mem_map(0x2000000,0x20000)
        image=XbeImage(self.patched)
        uc.mem_write(image.base,self.patched[:image.headers_size])
        for s in image.sections: uc.mem_write(s.start,self.patched[s.raw:s.raw+s.raw_size])
        uc.mem_protect(storage.VA,storage.CAPACITY,UC_PROT_READ)
        sentinel,stack=0x2010000,0x200F000
        uc.mem_write(sentinel,b'\x90')
        counts=[]
        def u32(at):return struct.unpack('<I',uc.mem_read(at,4))[0]
        def put(at,*values):uc.mem_write(at,struct.pack('<'+'I'*len(values),*values))
        def hook(machine,address,size,user):
            user[0]+=1
            if address==0x191D20:  # sole stub: select synthetic profile zero
                sp=machine.reg_read(UC_X86_REG_ESP)
                machine.reg_write(UC_X86_REG_EAX,0)
                machine.reg_write(UC_X86_REG_ESP,sp+4)
                machine.reg_write(UC_X86_REG_EIP,u32(sp))
        steps=[0]
        uc.hook_add(UC_HOOK_CODE,hook,steps)
        def call(va,ecx=0,edx=0,eax=0,budget=100000):
            put(stack,sentinel)
            for reg,value in ((UC_X86_REG_ESP,stack),(UC_X86_REG_EBP,0),(UC_X86_REG_ECX,ecx),
                              (UC_X86_REG_EDX,edx),(UC_X86_REG_EAX,eax)): uc.reg_write(reg,value)
            steps[0]=0
            uc.emu_start(va,sentinel,timeout=1000000,count=budget)
            self.assertEqual(uc.reg_read(UC_X86_REG_EIP),sentinel,hex(va))
            self.assertLess(steps[0],budget)
            counts.append(dict(va=hex(va),instructions=steps[0]))
            return uc.reg_read(UC_X86_REG_EAX)
        # Build actual native free/active lists, using all 400 retail pool nodes.
        pool,free,active=0xC3AC94,0xC3CBD4,0xC3CBE8
        for i in range(400):
            node=pool+i*20
            put(node,0,0,0,free if i==0 else node-20,free if i==399 else node+20)
        put(free+12,pool+399*20,pool)
        put(active+12,active,active)
        put(0xC3AC90,0)
        ids=music.identities(200)
        saved=[]
        for index,(collection,song) in enumerate(ids):
            identity=call(0x27F550,collection,song)
            item=struct.pack('<BBBBI',collection,song,1,0,identity)
            uc.mem_write(0xBC7E50+index*8,item);saved.append(item)
        uc.mem_write(0xBC7E50+200*8,bytes(8))
        uc.mem_write(0xBC7E4C,b'\x64')  # current playlist item 100
        call(0x280530)
        self.assertEqual(u32(0xC3CC04),200)
        self.assertEqual(u32(0xC3CBFC),pool+100*20)
        # Repeat native rebuild recycles the old 200 nodes without leaking pool.
        call(0x280530)
        self.assertEqual(u32(0xC3CC04),200)
        nodes=[];node=u32(active+16)
        while node != active:
            self.assertNotIn(node,nodes);nodes.append(node)
            self.assertTrue(pool<=node<pool+400*20)
            node=u32(node+16)
        self.assertEqual(len(nodes),200)
        for index,(collection,song) in enumerate(ids):
            node=call(0x27F900,index)  # actual scroll-offset list lookup
            self.assertEqual(node,nodes[index])
            self.assertEqual(call(0x27FA40,node),index)
            title=call(0x27F9A0,node)
            self.assertEqual(bytes(uc.mem_read(title,18)),f'Tone {index+1:03}\0'.encode('utf-16le'))
            # Execute native five-row viewport clamp for every valid offset.
            put(0xCB6D3C,max(0,index-4));put(0xCB6D34,min(index,4))
            call(0x329F20,eax=2)
            self.assertEqual(u32(0xCB6D3C)+u32(0xCB6D34),index)
            self.assertLessEqual(u32(0xCB6D34),4)
        self.assertEqual(call(0x27F900,200),0)
        call(0x27F3A0)  # real 400-entry profile write path; no I/O or save file
        self.assertEqual(bytes(uc.mem_read(0xBC7E50,200*8)),b''.join(saved))
        self.assertEqual(uc.mem_read(0xBC7E50+200*8+2,1),b'\0')
        self.assertEqual(uc.mem_read(0xBC7E4C,1),b'\x64')
        evidence=dict(status='PROVED / bounded',songs=200,pool_capacity=400,visible_playlist_rows=5,
                      collection_song_index_bits=8,profile_cursor_bits=8,sole_stub='0x191D20: profile zero',
                      native_calls=len(counts),max_instructions=max(c['instructions'] for c in counts),
                      builder_calls=[c for c in counts if c['va'] in ('0x280530','0x27f3a0')],
                      witness='No game, graphics, audio, filesystem or Xbox APIs executed')
        if os.environ.get('NFL2K5_MUSIC_EVIDENCE_DIR'):
            (Path(os.environ['NFL2K5_MUSIC_EVIDENCE_DIR'])/'bounded.json').write_text(json.dumps(evidence,indent=2)+'\n')


if __name__=='__main__': unittest.main()
