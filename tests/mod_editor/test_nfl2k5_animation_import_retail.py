"""Standalone private-evidence gates. Bounded reads; disposable compact copies only."""
from dataclasses import replace
from contextlib import ExitStack
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(REPO),str(REPO/'tests'),str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_animation as A, nfl2k5_animation_import as I
from mod_editor.core import nfl2k5_animation_bones as B, nfl2k5_animation_xbe as X, nfl2k5_models as M
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections,section_digest
from nfl2k5_xiso_fixture import SyntheticXiso
from test_nfl2k5_animation_retail import INDEX,INVENTORY,XBE
from test_nfl2k5_animation import NativeReferenceTests

DISC=Path(os.environ.get('NFL2K5_RETAIL_XISO','/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))


def require_assets(cls):
    for p in (INDEX,INVENTORY):
        if not p.is_file():raise unittest.SkipTest(f'Private animation evidence is absent: {p}')
    cls.source=A.AnimationSource(INDEX,INVENTORY)


class RetailImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):require_assets(cls)

    def test_gltf_roundtrip_and_edited_seed_pose_gates(self):
        for identity in ('archive:3107/27','archive:3092/163'):
            clip=self.source.load(identity);sk=self.source.skeleton(clip)
            with tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp)/'export';A.export_clip(clip,folder,sk)
                plan=I.compile_import(clip,folder/'primary.gltf',sk)
                self.assertEqual(plan.replacement.after,clip.original)
                p=folder/'primary.bin';data=bytearray(p.read_bytes());r=clip.roots[0]
                channel,frame=13,r.frames//2
                old=struct.unpack_from('<I',clip.body,r.rotations+4*(frame*r.channels+channel))[0]
                w,x,y,z=A.qm.unit(A.qm.decode(old+1))
                struct.pack_into('<4f',data,4*r.frames+16*(channel*r.frames+frame),x,y,z,w);p.write_bytes(data)
                edited=I.compile_import(clip,folder/'primary.gltf',sk)
                self.assertEqual(len(edited.replacement.receipt['changed_keys']),1)
                self.assertTrue(edited.receipt['pose_preflight']['passed'])
                print(identity,edited.receipt['pose_preflight'],flush=True)

    def test_real_disc_offsets_preflight_without_copy(self):
        if not DISC.is_file():self.skipTest(f'Private retail disc absent: {DISC}')
        c=self.source.load('archive:3107/27');p=I.author_referee_variant(c)
        edits=I.image_edits(DISC,(p,))
        self.assertEqual(edits[0].spans,((0x80bf6400,0,len(c.original)),))
        self.assertEqual(I.preflight_file(DISC,edits),['original','unchanged'])

    def test_authored_clip_compact_xiso_transport_and_replay(self):
        original=self.source.load('archive:3107/27')
        # All game bytes are actual bounded resource bytes; only directory placement
        # is synthetic. Six MiB, never a whole retail pack or a disc in memory.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);entries=[(i,b'x') for i in range(3107)]
            entries.extend(((int(original.source['outer_id'],0),original.original),(999,b'tail')))
            size=((2048+3109*2048+len(original.original)+0xffff)//0x10000)*0x10000
            fixture=SyntheticXiso(root,entries,pack_sizes=(size,),pack_sectors=(64,))
            source={**original.source,'chunk_offset':0,'outer_size':len(original.original),
                    'segments':[{'pack':'0','offset':fixture.entry_offsets[3107],'length':len(original.original)}]}
            clip=replace(original,source=source)
            export=root/'export';A.export_clip(clip,export,self.source.skeleton(original))
            # Untouched glTF is an exact whole-image roundtrip.
            p=I.compile_import(clip,export/'primary.gltf',self.source.skeleton(original))
            identity=root/'identity.iso';r=I.write_import_copy(p,fixture.path,identity)
            self.assertEqual(r['changed_bytes'],0);self.assertEqual(identity.read_bytes(),fixture.image)
            p=I.author_referee_variant(clip);out=root/'gesture.iso';r=I.write_import_copy(p,fixture.path,out)
            expected=bytearray(fixture.image);offset=fixture.virtual_to_image(fixture.entry_offsets[3107])
            expected[offset:offset+len(clip.original)]=p.replacement.after
            self.assertEqual(out.read_bytes(),expected)
            again=root/'again.iso';replay=I.write_import_copy(p,out,again)
            self.assertEqual(replay['changed_bytes'],0);self.assertEqual(out.read_bytes(),again.read_bytes())
            # Directory mutation must refuse even when the clip bytes still match.
            with fixture.path.open('r+b') as f:
                f.seek(fixture.pack_extent('0')+156+12*3107);f.write(struct.pack('<I',42))
            with self.assertRaisesRegex(A.AnimationError,'directory identity'):
                I.image_edits(fixture.path,(p,))

    def test_authored_pose_matches_independent_recovered_c(self):
        NativeReferenceTests.setUpClass();self.addCleanup(NativeReferenceTests.doClassCleanups)
        base=self.source.load('archive:3107/27');p=I.author_referee_variant(base)
        count=0;maximum=0.
        for mode in (0,1,4,5):
            raw=bytearray(p.replacement.after);raw[32+base.roots[0].offset+4]=(base.roots[0].flags&~5)|mode
            clip=A.parse_archive_span(raw,base.identity);r=clip.roots[0]
            payload=clip.body[r.rotations:r.rotations+4*r.channels*r.frames]
            storage=(ctypes.c_uint8*len(payload)).from_buffer_copy(payload)
            view=NativeReferenceTests.View(storage,len(payload),r.frames,r.channels,r.rate,r.multiplier,r.flags,r.duration)
            fun=NativeReferenceTests.lib.vc_nfl_coach_ref_pose_sample_title_policy
            fun.argtypes=[ctypes.POINTER(NativeReferenceTests.View),ctypes.c_float,ctypes.c_void_p,ctypes.c_void_p]
            fun.restype=ctypes.c_int
            times=[i/(2*r.rate*r.multiplier) for i in range(2*r.frames-1)]
            times += [r.duration-1e-6,r.duration,r.duration+1e-6,r.duration*3+.01]
            for t in times:
                result=(ctypes.c_float*100)();self.assertEqual(fun(ctypes.byref(view),t,result,None),0)
                expected=[v for q in A.sample_pose(clip,t) for v in q]
                error=max(abs(a-b) for a,b in zip(result,expected));maximum=max(maximum,error);count+=1
                self.assertLess(error,3e-6)
        print('Authored C pose comparisons:',count,'maximum component error',maximum,flush=True)


class EmbeddedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not XBE.is_file():raise unittest.SkipTest(f'Private retail XBE absent: {XBE}')
        cls.retail=XBE.read_bytes()

    def test_both_root_imports_repin_and_write_exact_copy(self):
        for clip in A.embedded_clips(XBE):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);folder=root/'export';A.export_clip(clip,folder)
                p=I.compile_import(clip,folder/'primary.gltf')
                same,r=X.apply(self.retail,p.replacement)
                self.assertEqual(same,self.retail);self.assertEqual(r['write_spans'],[])
                r0=clip.roots[0];data=bytearray((folder/'primary.bin').read_bytes())
                word=struct.unpack_from('<I',clip.body,r0.rotations)[0]
                w,x,y,z=A.qm.unit(A.qm.decode(word+1));struct.pack_into('<4f',data,r0.frames*4,x,y,z,w)
                (folder/'primary.bin').write_bytes(data);p=I.compile_import(clip,folder/'primary.gltf')
                changed,receipt=X.apply(self.retail,p.replacement)
                self.assertEqual(X.status(changed,p.replacement),'applied')
                self.assertEqual(X.apply(changed,p.replacement)[0],changed)
                self.assertTrue(all(section_digest(changed,s)==s.stored_digest for s in _sections(changed)))
                image=XbeImage(changed);site=image.offset(clip.source['span_va'],len(clip.original))
                allowed=set(range(site+r0.rotations,site+r0.rotations+4))
                section=next(s for s in _sections(changed) if s.raw_offset<=site<s.raw_offset+s.raw_size)
                allowed.update(range(section.header_offset+36,section.header_offset+56))
                self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(self.retail,changed)) if a!=b))
                output=root/'copy.xbe';r=X.write_import_copy(p,XBE,output)
                self.assertEqual(output.read_bytes(),changed);self.assertEqual(r['changed_bytes'],receipt['changed_bytes'])

    def test_foreign_digest_non_key_edits_and_reservation_overlap_refuse(self):
        p=X.default_replacement(self.retail)
        bad=bytearray(self.retail);bad[XbeImage(self.retail).section(0x86dfe0).raw+10]^=1
        self.assertEqual(X.status(bad,p),'foreign')
        with self.assertRaises(A.AnimationError):X.apply(bad,p)
        bad=bytearray(p.after);bad[0]^=1
        with self.assertRaisesRegex(A.AnimationError,'outside primary'):
            X.apply(self.retail,replace(p,after=bytes(bad)))
        manifest=json.loads((REPO/'data/nfl2k5_cave_reservations.json').read_text())
        manifest['spans'].append({'start':'0x86d540','end':'0x86d544','owner':'foreign','basis':'test'})
        with self.assertRaisesRegex(A.AnimationError,'overlaps reserved'):X.apply(self.retail,p,manifest=manifest)
        manifest['spans'][-1]['owner']=X.OWNER
        manifest['spans'].append({'start':'0x10634','end':'0x10648','owner':X.OWNER,'basis':'observed section digest'})
        self.assertEqual(X.status(self.retail,p,manifest=manifest),'retail')


class BoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_assets(cls)
        cls.models=M.ModelSource(INDEX,INVENTORY)
        cls.plan=B.compile_limb(cls.models)

    def test_both_lods_derived_joints_bind_skin_bounds_and_fixed_refit(self):
        low,high,skel=self.plan.members
        self.assertEqual([m.receipt['bind_array_bytes'] for m in (low,high)],[2800,6944])
        self.assertEqual(skel.before,skel.after);self.assertEqual(skel.receipt['axis_array_bytes'],400)
        self.assertEqual([m.receipt['vertices_changed'] for m in (low,high)],[1021,2278])
        self.assertTrue({f'l_forearm_twist_{n}' for n in (25,50,75,100)} <= {j['name'] for j in high.receipt['joints']})
        for m in (low,high):
            self.assertEqual(m.before[:32],m.after[:32]);self.assertEqual(len(m.before),len(m.after))
            self.assertLessEqual(m.receipt['fit']['exact_minimum_scratch'],16)
            self.assertLessEqual(m.receipt['fit']['padding_bytes'],16)
            self.assertLess(m.receipt['maximum_rest_skin_error_cm'],1e-4)
            self.assertAlmostEqual(m.receipt['forearm_length_after_cm']/m.receipt['forearm_length_before_cm'],1.01,places=6)
            self.assertNotEqual(m.receipt['bounds_before_cm'],m.receipt['bounds_after_cm'])
        raw={m.key:m.before for m in self.plan.members};edited,receipt=self.plan.apply(raw)
        self.assertEqual(self.plan.status(edited),'applied');self.assertEqual(self.plan.apply(edited)[0],edited)
        mixed=dict(edited);mixed[low.key]=low.before
        with self.assertRaisesRegex(A.AnimationError,'Mixed low/high'):self.plan.apply(mixed)
        for scale in (0,1.2,float('nan'),True):
            with self.assertRaises(A.AnimationError):B.compile_limb(self.models,scale)

    def test_no_edit_limb_preserves_both_whole_spans_and_skel(self):
        p=B.compile_limb(self.models,1.)
        self.assertTrue(all(m.before==m.after for m in p.members))
        self.assertEqual(p.status({m.key:m.before for m in p.members}),'unchanged')

    def test_derived_high_pose_graph_and_rebound_skin_are_finite(self):
        if not XBE.is_file():self.skipTest(f'Private retail XBE absent: {XBE}')
        compiler=shutil.which('cc') or shutil.which('gcc')
        if not compiler:self.skipTest('A C compiler is absent; recovered high-body graph comparison needs one')
        oracle=A._tool('nfl_player_92140_native_validate')
        image=XbeImage(XBE.read_bytes())
        self.assertEqual(image.sha256,A.RETAIL_XBE_SHA256)
        def floats(va,n):return list(struct.unpack(f'<{n}f',image.read(va,n*4)))
        table=oracle.Tables()
        table.low_to_high[:]=oracle.TITLE_MAP
        table.angle_lut[:]=floats(0x4e53e8,512)
        table.angle_coefficients[:]=floats(0x4e5c4c,6)
        table.local_constants[:]=floats(0x4ef8e0,351)
        table.projection_lower_clamp=floats(0x4e5c7c,1)[0]
        table.angle_scale=floats(0x4e696c,1)[0];table.blend_scale=floats(0x4e6d5c,1)[0]
        tables={'lut':list(table.angle_lut),'coeff':list(table.angle_coefficients),'local':list(table.local_constants),
                'clamp':table.projection_lower_clamp,'angle_scale':table.angle_scale,'blend_scale':table.blend_scale}
        vectors=[list(struct.unpack_from('<4f',self.plan.members[2].after,32+0x50+16*i)) for i in range(25)]
        skel=oracle.Skeleton(*(oracle.Vector(*v) for v in vectors))
        clip=self.source.load('archive:3092/163')
        hi=self.plan.members[1];resource,_,scene=self.models.parse(hi.key)
        body=self.models.decode_span(hi.after,resource);shape=scene['shapes'][0]
        lanes=M._shape_lanes(scene,shape,body);skin=M.decode_skin(body,shape,lanes,scene['submeshes'])
        points=M.read_positions(body,shape,lanes)
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as cleanup:
            library=(Path(tmp)/('high.dll' if os.name=='nt' else 'high.so')).resolve()
            subprocess.run([compiler,'-shared','-fPIC','-ffp-contract=off','-O0','-I',str(REPO/'include'),
                            str(REPO/'src/recovered/nfl2k5/player_local_postprocess.c'),'-lm','-o',str(library)],
                           check=True,capture_output=True)
            lib=ctypes.CDLL(str(library));fun=lib.vc_nfl_player_local_postprocess_92140
            if os.name=='nt':
                import _ctypes
                cleanup.callback(_ctypes.FreeLibrary,lib._handle)
            fun.argtypes=[ctypes.POINTER(oracle.Skeleton),ctypes.POINTER(oracle.Tables),ctypes.POINTER(oracle.Matrices),
                          oracle.TraceCallback,ctypes.c_void_p];fun.restype=ctypes.c_int
            count=0;maximum=0.
            for t in (0.,.033,.5,1.,2.,clip.roots[0].duration):
                low=[]
                for q in A.sample_pose(clip,t):
                    axes=[A.qm.rotate(A.qm.unit(q),v) for v in ((1,0,0),(0,1,0),(0,0,1))]
                    low.append([A.qm.f32(v) for row in axes for v in (*row,0.)]+[0.,0.,0.,1.])
                expected=oracle.oracle(vectors,tables,low,[[math.nan]*16 for _ in range(62)])
                matrices=oracle.Matrices()
                for i,m in enumerate(low):matrices.low[i][:]=m
                for m in matrices.high:m[:]=[math.nan]*16
                self.assertEqual(fun(ctypes.byref(skel),ctypes.byref(table),ctypes.byref(matrices),oracle.TraceCallback(),None),0)
                current=[]
                for i,(actual,wanted) in enumerate(zip(matrices.high,expected)):
                    for a,b in zip(actual,wanted):
                        self.assertTrue(math.isfinite(a) and math.isfinite(b))
                        maximum=max(maximum,abs(a-b));count+=1
                        self.assertLessEqual(abs(a-b),2.5e-4+abs(b)*2.5e-5)
                    local=list(actual);bone=skin.transforms[i]
                    local[12:15]=[a+b for a,b in zip(local[12:15],bone['local'])]
                    current.append(oracle.matmul(local,current[bone['parent']]) if bone['parent']>=0 else local)
                # Actual per-vertex palettes with edited inverse-bind translations.
                for point,influences in zip(points,skin.influences):
                    skinned=[0.,0.,0.]
                    for j,w in influences:
                        offset=[p-b for p,b in zip(point,skin.transforms[j]['absolute'])]
                        m=current[j]
                        for a in range(3):skinned[a]+=w*(sum(offset[b]*m[b*4+a] for b in range(3))+m[12+a])
                    self.assertTrue(all(math.isfinite(v) and abs(v)<10000 for v in skinned))
            print('High-body derived C comparisons:',count,'maximum component error',maximum,flush=True)

    def test_real_disc_both_lod_placement_and_compact_coordinated_copy(self):
        if DISC.is_file():
            edits=B.image_edits(self.plan,DISC)
            self.assertEqual([e.spans[0][0] for e in edits[:3]],[0x61540050,0x615612f0,0x615d4930])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);body=b''.join(m.before for m in self.plan.members)
            size=((len(body)+5*2048+0xffff)//0x10000)*0x10000
            f=SyntheticXiso(root,[(0,b'x'),(1,b'x'),(2,b'x'),(0x8ee9eeed,body),(4,b'tail')],
                            pack_sizes=(size,),pack_sectors=(64,))
            outer=A._tool('nfl_outer');archive=outer.parse_archive(f.retail_packs/'0')
            members=[];at=0
            for m in self.plan.members:
                seg=outer.range_segments(archive.packs,[0],f.entry_offsets[3]+at,len(m.before))
                source={**m.source,'outer_size':len(body),'chunk_offset':at,
                        'segments':[{'pack':s.pack_name,'offset':s.pack_offset,'length':s.size} for s in seg]}
                members.append(replace(m,segments=seg,source=source));at+=len(m.before)
            plan=replace(self.plan,members=tuple(members));out=root/'limb.iso'
            receipt=B.write_limb_copy(plan,f.path,out)
            expected=bytearray(f.image);at=f.virtual_to_image(f.entry_offsets[3])
            for m in members:expected[at:at+len(m.after)]=m.after;at+=len(m.after)
            self.assertEqual(out.read_bytes(),expected);self.assertGreater(receipt['changed_bytes'],0)
            self.assertEqual(f.path.read_bytes(),f.image)
            self.assertEqual(B.write_limb_copy(plan,out,root/'again.iso')['changed_bytes'],0)


if __name__=='__main__':unittest.main()
