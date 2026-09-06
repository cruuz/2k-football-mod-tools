"""Bounded common-resource and transactional archive proofs; no full disc copy."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from mod_editor.core import nfl2k5_guardian_resources as g
from mod_editor.core import nfl2k5_resource_growth as growth
from mod_editor.core import nfl2k5_models as models
from nfl2k5_xiso_fixture import dir_node, xiso
from tests.mod_editor.test_nfl2k5_guardian_overlay import roster

EXTRACTION=Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION","/media/noah/Storage/for codex 1.0/extracted"))/"ESPN NFL 2K5 (USA)"
PACK,XBE,DONOR=EXTRACTION/"vc_53450030/0",EXTRACTION/"default.xbe",EXTRACTION/"vc_53450030/B"


class ContractTests(unittest.TestCase):
    def test_foreign_or_mixed_collection_refuses_without_compile(self):
        for data in (b"",b"SCNE",bytes(g.RETAIL_SIZE)):
            self.assertEqual(g.collection_status(data),"foreign")
            with patch.object(g.cap,"_compile_model") as compiler:
                with self.assertRaises(ValueError):g.compile_collection(data)
                compiler.assert_not_called()

    def test_streaming_growth_rejects_invalid_index_and_live_gap(self):
        pack=bytearray(8192)
        struct.pack_into("<4I",pack,0,2,0,1,4)
        struct.pack_into("<6I",pack,0x9c,11,32,1,12,2048,3)
        def read(n,at):
            self.assertLessEqual(n,1024*1024)
            return bytes(pack[at:at+n])
        plan=growth.plan_pack0(read,len(pack),0,11,bytes(4096))
        self.assertEqual(plan.size_after,10240)
        for at in (0,12,0x9c,2048+32):
            saved=pack[at];pack[at]^=1
            with self.assertRaises(ValueError):growth.plan_pack0(read,len(pack),0,11,bytes(4096))
            pack[at]=saved


@unittest.skipUnless(PACK.is_file() and XBE.is_file() and DONOR.is_file(),"retail common models, helmet template and USA XBE absent")
class ResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with PACK.open("rb") as f:f.seek(g.RETAIL_START);cls.before=f.read(g.RETAIL_SIZE)
        with DONOR.open("rb") as f:
            t=g.cap.TARGETS[2];f.seek(t.pack_offset);cls.template=f.read(t.size)
        cls.after,cls.receipt=g.compile_collection(cls.before,cls.template)
        cls.xbe=XBE.read_bytes()
        cls.grown_xbe_size=len(g.runtime.apply(cls.xbe)[0])

    def test_both_lods_only_b_positions_change(self):
        for target in g.TARGETS:
            at=target.pack_offset-g.RETAIL_START
            old=self.before[at:at+target.size];new=self.after[at:at+target.size]
            self.assertEqual(old[:32],new[:32]);self.assertEqual(g.digest(new),target.applied_sha256)
            src=models.ModelSpanSource({target.key:old})
            resource,before,scene,shape,lanes,ids,positions=g.cap._shell(src,target)
            after,_=src._probe.decode_resource(new,resource)
            base=models._stream_base({},shape,lanes.position_stream)
            allowed={base+i*lanes.position_stride+lanes.position_offset+b for i in ids for b in range(6)}
            changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
            self.assertTrue(changed);self.assertLessEqual(changed,allowed)
            self.assertEqual(len(before),len(after))
            self.assertEqual(len(ids),target.shell_vertices)
            actual=models.read_positions(after,shape,lanes)
            self.assertTrue(all(actual[i]!=positions[i] for i in ids))
        # All 222 other native resources and every wrapper stay identical.
        old=list(g.archive.chunks(self.before));new=list(g.archive.chunks(self.after))
        self.assertEqual(len(new),225)
        for (i,at,a),(j,bt,b) in zip(old,new):
            self.assertEqual((i,at,a[:32]),(j,bt,b[:32]))
            if i not in (113,115):self.assertEqual(a,b)

    def test_native_texture_name_mips_and_palette_roundtrip(self):
        tx=models._tools_module("nfl_txtr")
        span=self.after[g.RETAIL_SIZE:];c=tx.parse_chunks(span)[0];body=tx.decode_chunk(span,c)[0]
        t=tx.parse_texture(body,c)
        self.assertEqual((t.name,t.format_name,t.width,t.height,t.mip_levels),("helmet01","P8",256,256,6))
        self.assertEqual((c.system_bytes,c.video_bytes,c.compressed,c.overlap_scratch_bytes),(128,88384,False,0))
        helmet=models._tools_module("nfl_live_helmet_txtr_png_import")
        levels=helmet.decode_levels(body)
        self.assertEqual([(m.width,m.height) for m in levels],[(s,s) for s in (256,128,64,32,16,8)])
        self.assertEqual(levels[0].rgba,g.cap.matte_cap_rgba())

    def test_replay_missing_mixed_foreign_resources(self):
        self.assertEqual(g.collection_status(self.before),"retail")
        self.assertEqual(g.collection_status(self.after),"applied")
        self.assertEqual(g.compile_collection(self.after)[0],self.after)
        for at in [g.TARGETS[0].pack_offset-g.RETAIL_START,g.TARGETS[1].pack_offset-g.RETAIL_START,g.RETAIL_SIZE,len(self.after)-1]:
            bad=bytearray(self.after);bad[at]^=1
            with self.assertRaises(ValueError):g.compile_collection(bad,self.template)
        with self.assertRaises(ValueError):g.compile_collection(self.before,None)
        bad=bytearray(self.after);t=g.TARGETS[0];at=t.pack_offset-g.RETAIL_START;bad[at:at+t.size]=self.before[at:at+t.size]
        with self.assertRaises(ValueError):g.compile_collection(bad,self.template)

    def test_real_4323_row_index_moves_virtual_offsets_and_preserves_other_packs(self):
        with PACK.open("rb") as f:
            def read(n,at):
                self.assertLessEqual(n,1024*1024)
                f.seek(at);return f.read(n)
            plan=growth.plan_pack0(read,PACK.stat().st_size,3,g.OUTER_ID,self.after,padding_bytes=(0,0x9f))
            table=read(len(plan.table),0)
        self.assertEqual(struct.unpack_from("<I",table)[0],4323)
        old_blocks=struct.unpack_from("<36I",table,12)
        new_blocks=struct.unpack_from("<36I",plan.table,12)
        self.assertEqual(old_blocks[1:],new_blocks[1:])
        self.assertEqual(new_blocks[0]-old_blocks[0],43)
        for i in range(4323):
            old=struct.unpack_from("<3I",table,0x9c+i*12)
            new=struct.unpack_from("<3I",plan.table,0x9c+i*12)
            self.assertEqual(new,(old[0],old[1]+(g.TEXTURE_SIZE if i==3 else 0),old[2]+(43 if i>3 else 0)))
        self.assertEqual(plan.size_after-plan.size_before,88064)
        self.assertEqual(plan.padding_byte,0x9f)

    def fixture(self,path,xbe=None):
        """~24 MiB capped fixture, real owned spans, synthetic neighboring packs."""
        xbe=self.xbe if xbe is None else xbe
        count=4003;cursor=g.archive.align_up(0x9c+count*12);entries=[]
        for i in range(count-1):
            length=g.RETAIL_SIZE if i==g.OUTER else len(roster())+32 if i==5 else 32
            entries.append((g.OUTER_ID if i==g.OUTER else i+1,length,cursor//2048))
            cursor=g.archive.align_up(cursor+length)
        pack_sizes=[cursor]+[2048]*14+[0x70000]
        entries.append((0x07e10847,sum(pack_sizes[1:]),cursor//2048))
        table=struct.pack("<3I36I",count,0,16,*[s//2048 for s in pack_sizes],*([0]*20))
        table+=b"".join(struct.pack("<3I",*e) for e in entries)
        pack_sector=64;sectors=[]
        for size in pack_sizes:sectors.append(pack_sector);pack_sector+=size//2048
        xsector=pack_sector;neighbor=xsector+(len(xbe)+2047)//2048
        sub=dir_node([(s,n,0x80,name) for s,n,name in zip(sectors,pack_sizes,"0123456789ABCDEF")])
        root=dir_node([(xsector,len(xbe),0x80,"default.xbe"),(34,len(sub),0x10,"vc_53450030"),(neighbor,8,0x80,"neighbor")])
        with path.open("wb") as f:
            f.seek(0x10000);f.write(xiso.XDVDFS_MAGIC);f.write(struct.pack("<II",33,len(root)))
            f.seek(0x107ec);f.write(xiso.XDVDFS_MAGIC)
            f.seek(33*2048);f.write(root);f.seek(34*2048);f.write(sub)
            f.seek(sectors[0]*2048);f.write(table)
            f.seek(sectors[0]*2048+entries[3][2]*2048);f.write(self.before)
            f.write(b"\x9f"*(g.archive.align_up(g.RETAIL_SIZE)-g.RETAIL_SIZE))
            body=roster()
            f.seek(sectors[0]*2048+entries[5][2]*2048)
            f.write(struct.pack("<4s7I",b"ROST",len(body),len(body),0,0,0,0,0)+body)
            f.seek(sectors[1]*2048+0x661b0);f.write(self.template)
            f.seek(xsector*2048);f.write(xbe);f.seek(neighbor*2048);f.write(b"KEEPTHIS")
        self.assertLess(path.stat().st_size,32*1024**2)
        return neighbor*2048

    def compiler(self,payload,template=None):
        # Reuse actual compiled 2.5 MiB resources, never retain complete packs.
        if g.collection_status(payload)=="applied":return bytes(payload),{"status":"already_applied"}
        self.assertEqual(payload,self.before);self.assertEqual(template,self.template)
        return self.after,self.receipt

    def test_streamed_paired_image_growth_all_outer_mappings_and_replay(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,"compile_collection",new=self.compiler):
            path=(Path(tmp)/"fixture.iso").resolve();neighbor=self.fixture(path)
            with g.archive.Disc(path,descriptors=()) as disc:
                old=[(e.name_id,e.size,e.virtual_offset) for e in disc.archive_entries]
                blocks=[p.size for p in disc.packs]
            self.assertEqual(g.image_status(path),"retail")
            receipt=g.apply_to_image(path);self.assertEqual(receipt["status"],"applied")
            self.assertEqual(receipt["pack_transport"]["pack_growth"],88064)
            self.assertEqual(g.image_status(path),"applied")
            with path.open("rb") as f:f.seek(neighbor);self.assertEqual(f.read(8),b"KEEPTHIS")
            with g.archive.Disc(path,descriptors=()) as disc:
                self.assertEqual([p.size for p in disc.packs][1:],blocks[1:])
                for i,(before,e) in enumerate(zip(old,disc.archive_entries)):
                    identity,size,offset=before
                    self.assertEqual(e.name_id,identity)
                    self.assertEqual(e.size,size+(g.TEXTURE_SIZE if i==3 else 0))
                    self.assertEqual(e.virtual_offset,offset+(88064 if i>3 else 0))
                donor=disc.archive_entries[4002]
                self.assertEqual(disc.read_entry_range(donor,0x661b0,len(self.template)),self.template)
            self.assertEqual(g.apply_to_image(path)["image_growth"],0)
            os.replace(path,path.with_suffix(".closed"))

    def test_partial_write_rollback_at_pack_node_and_xbe_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,"compile_collection",new=self.compiler):
            path=(Path(tmp)/"failure.iso").resolve()
            for mode in ("pack","pack_node","xbe","xbe_node","same_size_xbe"):
                xbe=g.runtime.space.apply(self.xbe,g.runtime.REQUESTS,scaleout=True)[0] if mode=="same_size_xbe" else None
                self.fixture(path,xbe);before=g.archive.file_hash(path);size=path.stat().st_size
                real=g.io.pwrite;failed=False;nodes=0
                def fail(fd,data,at):
                    nonlocal failed,nodes
                    if len(data)==8:nodes+=1
                    hit=(mode=="pack" and len(data)>128 or mode=="pack_node" and nodes==1 and len(data)==8
                         or mode in ("xbe","same_size_xbe") and len(data)==self.grown_xbe_size
                         or mode=="xbe_node" and nodes==2 and len(data)==8)
                    if not failed and hit:
                        failed=True;real(fd,data[:3],at);return 3
                    return real(fd,data,at)
                with patch.object(g.io,"pwrite",new=fail),self.assertRaises(ValueError):g.apply_to_image(path)
                self.assertTrue(failed,mode);self.assertEqual(path.stat().st_size,size)
                self.assertEqual(g.archive.file_hash(path),before,mode)
            os.replace(path,path.with_suffix(".closed"))

    def test_paired_roster_selection_survives_growth_replay_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,"compile_collection",new=self.compiler):
            path=(Path(tmp)/"players.iso").resolve();self.fixture(path)
            body=roster();selection=dict(pool="primary",index=1,record_sha256=g.digest(body[0x154:0x1a8]))
            g.apply_to_image(path,guardian_players=[selection])
            with g.archive.Disc(path,descriptors=()) as disc:
                e=disc.archive_entries[5];after=disc.read_entry_range(e,32,e.size-32)
            self.assertTrue(g.runtime.record_selected(after[0x154:0x1a8]))
            self.assertEqual(g.apply_to_image(path,guardian_players=[selection])["image_growth"],0)
            cleared=g.apply_to_image(path,guardian_players=[])
            self.assertEqual(cleared["pack_transport"]["pack_growth"],0)
            with g.archive.Disc(path,descriptors=()) as disc:
                e=disc.archive_entries[5];self.assertEqual(disc.read_entry_range(e,32,e.size-32),body)
            before=g.archive.file_hash(path)
            with self.assertRaises(ValueError):g.apply_to_image(path,guardian_players=[{**selection,"record_sha256":"0"*64}])
            with self.assertRaisesRegex(ValueError,"owner union"):
                g.apply_to_image(path,extra_requests=(("missing_owner","code",16,16),))
            self.assertEqual(g.archive.file_hash(path),before)


if __name__=="__main__":unittest.main()
