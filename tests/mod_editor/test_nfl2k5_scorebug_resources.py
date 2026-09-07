"""Standalone runtime TXTR, complete archive index and disc transaction tests."""
from __future__ import annotations
import hashlib
import importlib.util
from contextlib import ExitStack
import os
import shutil
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from mod_editor.core import nfl2k5_scorebug_resources as a
from mod_editor.core import nfl2k5_scorebug_ingame as r
from mod_editor.core import nfl2k5_scorebug_runtime as runtime
from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
from mod_editor.core import platform_compat as io
from mod_editor.core import nfl2k5_depth_chart_storage as storage
from tools import nfl_outer as outer
from nfl2k5_xiso_fixture import dir_node

EXTRACTION=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'
PACK,XBE=EXTRACTION/'vc_53450030/0',EXTRACTION/'default.xbe'


class PublicTests(unittest.TestCase):
    def test_invalid_names_and_foreign_extents_refuse(self):
        self.assertEqual(a.runtime_pack_status(b'bad'),'foreign')
        with self.assertRaises(ValueError):a.compile_runtime_collection(b'bad')
        for code,side,n in [('31','away',3),('20','bad',1),('20','away',-1),('37','home',True)]:
            with self.assertRaises(ValueError):a.runtime_panel_name(code,side,n)
        self.assertEqual(a.RUNTIME_GROWTH%2048,0)


@unittest.skipUnless(PACK.is_file() and XBE.is_file() and importlib.util.find_spec('PIL'),
                     'retail pack 0, USA XBE and Pillow required')
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The compiler returns a lazy composition. No whole pack is materialized.
        stack=ExitStack();cls.addClassCleanup(stack.close)
        cls.before_file=stack.enter_context(PACK.open('rb'))
        cls.before=a.PackView.from_fd(cls.before_file.fileno(),0,PACK.stat().st_size)
        cls.xbe=XBE.read_bytes()
        view=a.PackView.from_fd(cls.before_file.fileno(),0,len(cls.before))
        cls.after,cls.receipt=a.compile_runtime_collection(view)
        # Keep the actual compiler's lazy view for the complete real-pack
        # index/suffix checks. Disk transactions use a sparse fixture carrying
        # every pinned input plus XDVDFS neighbours, not a retained pack copy.
        # These IO substitutions only preserve holes; every read/hash/assertion
        # still sees the exact logical file, including all zero bytes.
        real_write=io.pwrite
        def sparse_write(fd,data,offset):
            if offset >= os.fstat(fd).st_size and not any(data):
                os.ftruncate(fd,offset+len(data));return len(data)
            return real_write(fd,data,offset)
        def sparse_copy(source,target):
            with Path(source).open('rb') as src,Path(target).open('wb') as dst:
                while block:=src.read(a.READ_BLOCK):
                    if any(block):dst.write(block)
                    else:dst.seek(len(block),1)
                dst.truncate()
            return str(target)
        stack.enter_context(patch.object(io,'pwrite',new=sparse_write))
        stack.enter_context(patch.object(shutil,'copyfile',new=sparse_copy))
    def test_all_264_native_objects_identity_pixels_and_dimming(self):
        start=a.HUD_START+a.HUD_SIZE
        objects=r.tx.parse_chunks(self.after[start:start+a.RUNTIME_APPEND_SIZE])
        self.assertEqual(len(objects),264)
        names=set()
        for c in objects:
            d=r.tx.decode_chunk(self.after[start:start+a.RUNTIME_APPEND_SIZE],c)[0]
            tex=r.tx.parse_texture(d,c);names.add(tex.name)
            self.assertEqual((c.system_bytes,c.video_bytes,c.compressed,c.overlap_scratch_bytes),(128,5120,False,0))
            self.assertEqual((tex.width,tex.height,tex.format_name,tex.mip_levels),(128,32,'P8',1))
            rgba=r.tx.texture_to_rgba(d,c,tex)
            side=tex.name[4];count=int(tex.name[5])
            for n,x in enumerate((91,101,111)):
                dx=(x if side=='a' else 127-x-6)+3
                pixel=rgba[(28*128+dx)*4:(28*128+dx)*4+4]
                self.assertEqual(pixel[3],255)
                self.assertGreater(min(pixel[:3]),180) if n<count else self.assertLess(max(pixel[:3]),90)
        self.assertEqual(names,{rec['name'] for rec in self.receipt['resources']})
        self.assertEqual(len(names),264)
        # Source logos are still present unchanged in the archive.
        for rec in a.TEAM_LOGOS.values():
            at,size=rec['pack_offset'],rec['span_size']
            self.assertEqual(self.before[at:at+size],self.after[at:at+size])
    def test_index_maps_every_unchanged_outer_to_identical_physical_pack_offsets(self):
        n=struct.unpack('<I',self.before[:4])[0]
        before_blocks=struct.unpack('<36I',self.before[12:156])
        after_blocks=struct.unpack('<36I',self.after[12:156])
        self.assertEqual(after_blocks[1:],before_blocks[1:])
        self.assertEqual(after_blocks[0]-before_blocks[0],a.RUNTIME_GROWTH//2048)
        def packs(blocks):
            at=0;result=[]
            for i,blocks in enumerate(blocks):
                if not blocks:break
                result.append(outer.Pack(i,outer.PACK_NAMES[i],blocks,blocks*2048,at,Path('unused')));at+=blocks*2048
            return tuple(result)
        bp,ap=packs(before_blocks),packs(after_blocks)
        for i in range(n):
            off=outer.HEADER_SIZE+i*12
            bid,bsz,boff=struct.unpack('<III',self.before[off:off+12])
            aid,asz,aoff=struct.unpack('<III',self.after[off:off+12])
            self.assertEqual(aid,bid)
            if i==a.HUD_OUTER_INDEX:
                self.assertEqual((asz, aoff),(bsz+a.RUNTIME_APPEND_SIZE,boff));continue
            self.assertEqual(asz,bsz)
            self.assertEqual(aoff,boff+(a.RUNTIME_GROWTH//2048 if i>a.HUD_OUTER_INDEX else 0))
            old=outer.range_segments(bp,[p.virtual_start for p in bp],boff*2048,bsz)
            new=outer.range_segments(ap,[p.virtual_start for p in ap],aoff*2048,asz)
            self.assertEqual(len(old),len(new))
            for x,y in zip(old,new):
                self.assertEqual((x.pack_name,x.size),(y.pack_name,y.size))
                self.assertEqual(y.pack_offset,x.pack_offset+(a.RUNTIME_GROWTH if i>a.HUD_OUTER_INDEX and x.pack_ordinal==0 else 0))
        end=outer.align_up(a.HUD_START+a.HUD_SIZE)
        for at in range(end,len(self.before),1024*1024):
            count=min(1024*1024,len(self.before)-at)
            self.assertTrue(self.after[at+a.RUNTIME_GROWTH:at+a.RUNTIME_GROWTH+count]==self.before[at:at+count],
                            f'unchanged pack suffix differs at {at:#x}')
        # Wrapper and chunk order are unchanged for all 139 existing resources.
        old=r.tx.parse_chunks(self.before[a.HUD_START:a.HUD_START+a.HUD_SIZE])
        new=r.tx.parse_chunks(self.after[a.HUD_START:a.HUD_START+a.HUD_SIZE+a.RUNTIME_APPEND_SIZE])
        self.assertEqual(old,new[:139])
        for i,c in enumerate(old):
            if i not in (53,78):
                at=a.HUD_START+c.offset
                self.assertEqual(self.before[at:at+(c.stored_size+32)],self.after[at:at+(c.stored_size+32)])
    def test_status_replay_and_corruption_at_each_owned_boundary(self):
        self.assertEqual(a.runtime_pack_status(self.before),'retail')
        self.assertEqual(a.runtime_pack_status(self.after),'applied')
        self.assertIs(a.compile_runtime_collection(self.after)[0],self.after)
        for off in (0,12,outer.HEADER_SIZE+a.HUD_OUTER_INDEX*12+4,
                    outer.HEADER_SIZE+(a.HUD_OUTER_INDEX+1)*12+8,
                    a.RESOURCES['score_bug']['pack_offset'],a.RESOURCES['score_buga']['pack_offset'],
                    a.HUD_START+a.HUD_SIZE,a.HUD_START+a.HUD_SIZE+a.RUNTIME_APPEND_SIZE):
            self.assertEqual(a.runtime_pack_status(self.corrupt(self.after,off)),'foreign',hex(off))
        wrong=self.corrupt(self.before,a.TEAM_LOGOS['LV']['pack_offset'])
        with self.assertRaises(r.ScorebugError):a.compile_runtime_collection(wrong)
        with self.assertRaisesRegex(ValueError,'whole-pack read'):
            self.before[:]
    @staticmethod
    def corrupt(source, off):
        def read(n, at):
            data=bytearray(source[at:at+n])
            if at <= off < at+n:data[off-at]^=1
            return bytes(data)
        return a.PackView(len(source),read)
    def image(self,path,xbe=None):
        xbe=self.xbe if xbe is None else xbe
        pack_sector=64;xs=pack_sector+len(self.before)//2048
        neighbor=xs+(len(xbe)+2047)//2048
        root=dir_node([(xs,len(xbe),0x80,'default.xbe'),(34,32,0x10,'vc_53450030'),(neighbor,8,0x80,'neighbour')])
        sub=dir_node([(pack_sector,len(self.before),0x80,'0')])
        with path.open('wb') as f:
            f.seek(0x10000);f.write(r.layout.xc.XDVDFS_MAGIC)
            f.write(struct.pack('<II',33,len(root)));f.seek(0x107ec);f.write(r.layout.xc.XDVDFS_MAGIC)
            f.seek(33*2048);f.write(root);f.seek(34*2048);f.write(sub.ljust(32,b'\0'))
            extents=[(0,outer.HEADER_SIZE+4323*12),(a.HUD_START,a.HUD_SIZE)]
            extents += [(v['pack_offset'],v['span_size']) for v in a.TEAM_LOGOS.values()]
            for offset,size in extents:
                f.seek(pack_sector*2048+offset);f.write(self.before[offset:offset+size])
            f.seek(xs*2048);f.write(xbe)
            f.seek(neighbor*2048);f.write(b'KEEPTHIS')
        return neighbor*2048
    def test_disc_growth_replay_and_rollback_at_pack_node_and_xbe_writes(self):
        # Compiler itself ran above. Reuse its exact immutable output so failure
        # injection exercises IO rather than repeating artwork quantization.
        real_compile=a.compile_runtime_collection
        def compile(pack, *, probe='full'):
            state=a.runtime_pack_status(pack)
            if state=='applied':return pack,{'status':'already_applied','changed_bytes':0}
            self.assertEqual(state,'retail');return real_compile(pack,probe=probe)
        # A Mock retains every argument in call_args_list, including each
        # complete 194 MB pack. These replacements need no call history.
        with tempfile.TemporaryDirectory() as tmp,patch.object(a,'compile_runtime_collection',new=compile):
            path=(Path(tmp)/'copy.iso').resolve()
            neighbor=self.image(path)
            self.assertEqual(r.runtime_image_status(path),'retail')
            rec=r.runtime_apply_in_place(path,with_kickoff=True)
            self.assertEqual(rec['status'],'applied');self.assertGreater(rec['image_growth'],0)
            self.assertEqual(r.runtime_image_status(path),'applied')
            with path.open('rb') as f:
                entries,_=r.layout.xc.parse_xdvdfs(f.fileno(),path.stat().st_size)
                f.seek(entries['default.xbe'].byte_offset);xbe=f.read(entries['default.xbe'].size)
                self.assertEqual(runtime.status(xbe),'applied');self.assertEqual(kickoff.status(xbe),'applied')
                f.seek(neighbor);self.assertEqual(f.read(8),b'KEEPTHIS')
            size=path.stat().st_size
            self.assertEqual(r.runtime_apply_in_place(path,with_kickoff=True)['image_growth'],0)
            self.assertEqual(path.stat().st_size,size)
            # Installing another already-reserved XBE owner must not append the
            # unchanged pack, or require a nonexistent resource-change receipt.
            self.image(path)
            r.runtime_apply_in_place(path,extra_requests=kickoff.REQUESTS)
            with path.open('rb') as f:
                entries,_=r.layout.xc.parse_xdvdfs(f.fileno(),path.stat().st_size)
                pack_offset=entries['vc_53450030/0'].byte_offset
            rec=r.runtime_apply_in_place(path,with_kickoff=True)
            self.assertEqual(rec['image_growth'],0)
            self.assertEqual(rec['pack_offset'],pack_offset)
            with path.open('rb') as f:
                entries,_=r.layout.xc.parse_xdvdfs(f.fileno(),path.stat().st_size)
                x=entries['default.xbe'];f.seek(x.byte_offset)
                self.assertEqual(kickoff.status(f.read(x.size)),'applied')
            for mode in ('pack','pack_node','xbe','xbe_node','same_size_xbe'):
                xbe=runtime.space.apply(self.xbe,runtime.REQUESTS)[0] if mode=='same_size_xbe' else None
                self.image(path,xbe)
                before_size=path.stat().st_size
                with path.open('rb') as f:before_sha=hashlib.file_digest(f,'sha256').hexdigest()
                real=io.pwrite;failed=False;nodes=0
                def fail(fd,data,off):
                    nonlocal failed,nodes
                    if len(data)==8:nodes+=1
                    hit=(mode=='pack' and off==(before_size+2047)&-2048 and len(data)==a.READ_BLOCK
                         or mode=='pack_node' and nodes==1 and len(data)==8
                         or mode in ('xbe','same_size_xbe') and len(data)==runtime.space.FILE_SIZE
                         or mode=='xbe_node' and nodes==2 and len(data)==8)
                    if not failed and hit:
                        failed=True;real(fd,data[:3],off);return 3
                    return real(fd,data,off)
                with patch.object(io,'pwrite',new=fail),self.assertRaises(ValueError):r.runtime_apply_in_place(path)
                self.assertTrue(failed,mode);self.assertEqual(path.stat().st_size,before_size)
                with path.open('rb') as f:self.assertEqual(hashlib.file_digest(f,'sha256').hexdigest(),before_sha,mode)
            os.replace(path,path.with_suffix('.closed'))

    def test_all_probe_sets_are_exact_idempotent_and_refuse_other_profiles(self):
        from tools import nfl2k5_scorebug_reference as cli
        with tempfile.TemporaryDirectory() as directory:
            path=(Path(directory)/'probe.iso').resolve()
            for probe in a.PROBES:
                count, appendix, growth=a.probe_sizes(probe)
                compiled, receipt=a.compile_runtime_collection(self.before,probe=probe)
                self.assertEqual(len(compiled),r.PACK_SIZE+growth)
                self.assertEqual(receipt['texture_count'],count)
                self.assertEqual(len(receipt['resources']),count)
                self.assertEqual(receipt['native_heap_bytes'],count*5376)
                self.assertEqual(a.runtime_pack_status(compiled,probe=probe),'applied')
                self.assertIs(a.compile_runtime_collection(compiled,probe=probe)[0],compiled)
                names={item['name'] for item in receipt['resources']}
                self.assertEqual(names,{a.runtime_panel_name(code,side,n) for code in a.probe_codes(probe)
                                        for side in ('home','away') for n in range(4)})
                for other in a.PROBES:
                    same=a.probe_codes(probe)==a.probe_codes(other)
                    self.assertEqual(a.runtime_pack_status(compiled,probe=other),'applied' if same else 'foreign')
                self.image(path)
                if probe=='transport':
                    # Logical XDVDFS extents remain valid with trailing rip padding.
                    with path.open('r+b') as f:f.truncate(path.stat().st_size+458752)
                target=path.with_name('installed.iso')
                installed=cli.apply_copy(path,target,runtime_probe=probe)
                self.assertEqual(r.runtime_image_status(path,probe=probe),'retail')
                path.unlink()
                os.replace(target,path)
                self.assertEqual(installed['hooks_installed'],a.probe_has_hooks(probe))
                self.assertEqual(r.runtime_image_status(path,probe=probe),'applied')
                self.assertEqual(r.runtime_apply_in_place(path,probe=probe)['image_growth'],0)
                with path.open('rb') as f:
                    entries,_=r.layout.xc.parse_xdvdfs(f.fileno(),path.stat().st_size)
                    x=entries['default.xbe'];f.seek(x.byte_offset);xbe=f.read(x.size)
                for va,original in runtime.HOOKS.values():
                    off=r.layout.sbpos.va_to_off(xbe,va)
                    self.assertEqual(xbe[off:off+5]==original,not a.probe_has_hooks(probe))
                path.unlink()


if __name__=='__main__':unittest.main()
