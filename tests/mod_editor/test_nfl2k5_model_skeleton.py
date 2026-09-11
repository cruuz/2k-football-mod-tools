"""Standalone bind-import gates. No retail fixtures or retail bytes are shipped."""
from __future__ import annotations

import base64
import copy
import ctypes
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO),str(REPO/'tools'),str(REPO/'tests'),str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_models as M, nfl2k5_model_skeleton as S, nfl2k5_animation_bones as B
from mod_editor.core import nfl2k5_animation as A


def synthetic_transforms():
    # Authored test coordinates, not a retail bind table.
    rows = [('root',-1,(0,0,0)),('lfemur',0,(10,-5,0)),('ltibia',1,(10,-45,0)),
            ('lfoot',2,(10,-85,0)),('ltoes',3,(10,-90,15)),
            ('rfemur',0,(-10,-5,0)),('rtibia',5,(-10,-45,0)),('rfoot',6,(-10,-85,0)),('rtoes',7,(-10,-90,15)),
            ('waist',0,(0,10,0)),('thorax',9,(0,35,0)),('neck',10,(0,55,0)),('head',11,(0,65,0)),
            ('lcollar',10,(8,48,0)),('lhumerus',13,(20,50,0)),('lelbow',14,(45,50,0)),('lwrist',15,(60,50,0)),('lhand',16,(70,50,0)),
            ('rcollar',10,(-8,48,0)),('rhumerus',18,(-20,50,0)),('relbow',19,(-45,50,0)),('rwrist',20,(-60,50,0)),('rhand',21,(-70,50,0)),
            ('lshoulderpad',10,(15,55,0)),('rshoulderpad',10,(-15,55,0))]
    return [{'name':n,'index':i,'parent':p,'absolute':tuple(float(v) for v in xyz),
             'local':tuple(float(a-b) for a,b in zip(xyz,rows[p][2] if p>=0 else (0,0,0)))} for i,(n,p,xyz) in enumerate(rows)]


def fixture_document(transforms, tag='synthetic-export'):
    binary = b''.join(struct.pack('<16f',1,0,0,0,0,1,0,0,0,0,1,0,*(-v for v in t['absolute']),1) for t in transforms)
    nodes = [{'name':'test:'+t['name'],'translation':list(t['local'])} for t in transforms]
    for t in transforms:
        if t['parent']>=0:
            nodes[t['parent']].setdefault('children',[]).append(t['index'])
    nodes.append({'name':M.ROOT_NODE_NAME,'scale':[.01]*3,'children':[0],'extras':{S.EXPORT_TAG:tag}})
    return {'asset':{'version':'2.0'},'nodes':nodes,'skins':[{'joints':list(range(len(transforms))),'inverseBindMatrices':0}],
            'buffers':[{'uri':'data:application/octet-stream;base64,'+base64.b64encode(binary).decode(),'byteLength':len(binary)}],
            'bufferViews':[{'buffer':0,'byteLength':len(binary)}],
            'accessors':[{'bufferView':0,'componentType':5126,'count':len(transforms),'type':'MAT4'}]}


def author(doc, transforms, targets):
    for t in transforms:
        node = next(n for n in doc['nodes'] if n.get('name','').endswith(':'+t['name']))
        parent = targets[transforms[t['parent']]['name']] if t['parent']>=0 else (0.,)*3
        node['translation'] = [a-b for a,b in zip(targets[t['name']],parent)]


def body_set():
    return M.BodySet(3,tuple(M.ModelEntry(k,3,int(k[3:]),n,'players',0,0) for k,n in
                           (('o3c113','lo_body'),('o3c114','hi_body'),('o3c115','hi_head'))))


class SyntheticTests(unittest.TestCase):
    def test_bounds_directions_and_unsupported_bones(self):
        ts = synthetic_transforms()
        for bone in S.BONES:
            for scale in (.95,1.05):
                got,number = S.infer_edit(ts,S.target_positions(ts,bone,scale))
                self.assertEqual(got,bone)
                self.assertAlmostEqual(number,scale,places=6)
            with self.assertRaisesRegex(M.ModelsError,'proved.*5%'):
                S.infer_edit(ts,S.target_positions(ts,bone,1.051))
        target = {t['name']:t['absolute'] for t in ts}
        target['lhand'] = (70,51,0)
        with self.assertRaisesRegex(M.ModelsError,'direction change'):
            S.infer_edit(ts,target)
        for name in ('root','neck','head','thorax','lshoulderpad'):
            target = {t['name']:t['absolute'] for t in ts}
            target[name] = tuple(v+1 for v in target[name])
            with self.assertRaisesRegex(M.ModelsError,'non-limb'):
                S.infer_edit(ts,target)

    def test_gltf_glb_noop_and_named_refusals(self):
        ts = synthetic_transforms()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'test.gltf'
            original = fixture_document(ts)
            def read(doc):
                S._json(path,doc)
                return S.read_bind(M.GltfFile(path),ts,'test')
            expected = {t['name']:t['absolute'] for t in ts}
            self.assertLess(max(math.dist(p,expected[n]) for n,p in read(original).items()),1e-10)
            payload = json.dumps(original).encode(); payload += b' '*(-len(payload)%4)
            glb = Path(tmp)/'test.glb'
            glb.write_bytes(struct.pack('<4sIII',b'glTF',2,20+len(payload),len(payload))+struct.pack('<I',0x4e4f534a)+payload)
            self.assertLess(max(math.dist(p,expected[n]) for n,p in S.read_bind(M.GltfFile(glb),ts,'test').items()),1e-10)
            cases = [('joint name change',lambda d:d['nodes'][1].update(name='renamed')),
                     ('rotation or scale',lambda d:d['nodes'][1].update(rotation=[0,0,.1,.995])),
                     ('rotation or scale',lambda d:d['nodes'][1].update(scale=[1.01,1,1])),
                     ('topology',lambda d:d['nodes'][1]['children'].append(0)),
                     ('topology',lambda d:d['skins'][0]['joints'].pop()),
                     ('nonfinite',lambda d:d['nodes'][1].update(translation=[float('nan'),0,0])),
                     ('animation edits',lambda d:d.update(animations=[{}]))]
            for reason,change in cases:
                doc = copy.deepcopy(original); change(doc)
                # Deliberately write nonfinite JSON to exercise hostile-input refusal.
                path.write_text(json.dumps(doc),encoding='utf-8')
                with self.assertRaisesRegex(M.ModelsError,reason):
                    S.read_bind(M.GltfFile(path),ts,'test')

    def test_synthetic_noop_complete_import_is_byte_identical(self):
        """Synthetic byte buffers exercise the full paired import, including _rewrite.

        Decode adapters describe these artificial buffers; the glTF reader,
        pairing, edit inference, bind serialization and transaction are real.
        """
        ts = synthetic_transforms(); bs = body_set()
        body = bytearray(0x80+112*25)
        # Relative pointer +0x64 -> bind +0x80; one authored position at +0.
        struct.pack_into('<i',body,0x64,0x80-0x64+1)
        for t in ts:
            struct.pack_into('<3f',body,0x80+t['index']*112+0x40,*t['absolute'])
            struct.pack_into('<3f',body,0x80+t['index']*112+0x50,*t['local'])
        body = bytes(body); span = b'W'*32+body
        skel = b'S'*112+b'\0'*400
        lanes = SimpleNamespace(name='test',record_offset=0,transform_count=25,vertex_count=1,
                                position_stream=0,position_stride=6,position_offset=0,position_format='NORMSHORT3',
                                scale=1.,offset=(0.,)*3,normal=None)
        skin = SimpleNamespace(transforms=ts,influences=[[(0,1.)]],notes=[])
        resources = {key:SimpleNamespace(outer_index=3,chunk_index=int(key[3:]),outer_id='0x1',outer_size=len(span),chunk_offset=0)
                     for key in (*bs.keys,'o3c116')}
        source = SimpleNamespace(inventory_path='unused',
             span=lambda r:skel if r.chunk_index==116 else span,
             decode_span=lambda raw,r:raw[32:],archive_segments=lambda r:())
        source.parse = lambda key:(resources[key],body,{'shapes':[{}],'submeshes':[]})
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for entry in bs.entries:
                S._json(folder/M.body_set_file_name(entry),fixture_document(ts))
            S._json(folder/S.MANIFEST,{'schema':S.SCHEMA,'export_id':'synthetic-export',
                                     'members':{k:{'decoded_sha256':M._sha256(body)} for k in bs.keys}})
            parse = lambda key:(resources[key],body,{'shapes':[{}],'submeshes':[]},{},lanes,skin)
            real_tool = M._tools_module
            def tool(name):
                if name=='nfl_scene_probe':
                    return SimpleNamespace(parse_inventory=lambda path:({},list(resources.values())))
                return real_tool(name)
            with patch.object(S,'_skin',side_effect=lambda s,k:parse(k)), patch.object(M,'_shape_lanes',return_value=lanes), \
                 patch.object(M,'decode_skin',return_value=skin), patch.object(M,'read_positions',return_value=[(0.,0.,0.)]), \
                 patch.object(M,'compile_import',side_effect=M.UnchangedModelError('synthetic no-op')), \
                 patch.object(M,'_tools_module',side_effect=tool), \
                 patch.object(B,'BODY_PINS',{k:(25,1,0x80,M._sha256(body)) for k in ('o3c113','o3c114')}), \
                 patch.object(S,'HEAD_SHA256',M._sha256(body)), \
                 patch.object(B,'SKEL_SHA256',M._sha256(skel)):
                compiled = M.compile_body_set_import(source,bs,folder,import_skeleton=True)
            plan = compiled.skeleton_plan
            self.assertEqual(compiled.changed_bytes,0)
            self.assertEqual(plan.receipt['changed_bones'],[])
            for member in plan.members:
                self.assertEqual(member.before,member.after)
            inputs = {m.key:m.before for m in plan.members}
            self.assertEqual(plan.apply(inputs)[0],inputs)


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_nfl2k5_animation_retail import INDEX,INVENTORY,XBE
        for p in (INDEX,INVENTORY,XBE):
            if not p.is_file():
                raise unittest.SkipTest(f'Private skeleton evidence absent: {p}')
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler:
            raise unittest.SkipTest('Recovered-C skeleton gate needs a C compiler')
        try:
            import unicorn
        except ImportError:
            raise unittest.SkipTest('Native skeleton gate needs Unicorn')
        cls.temp = tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)/'export'; cls.folder.mkdir()
        cls.source = M.ModelSource(INDEX,INVENTORY); cls.xbe = XBE
        cls.bs = body_set()
        M.export_body_set(cls.source,cls.bs,cls.folder)
        cls.docs = {e.key:json.loads((cls.folder/M.body_set_file_name(e)).read_text()) for e in cls.bs.entries}
        cls.transforms = {e.key:S._skin(cls.source,e.key)[-1].transforms for e in cls.bs.entries}
        libpath = (Path(cls.temp.name)/('gate.dll' if os.name=='nt' else 'gate.so')).resolve()
        subprocess.run([compiler,'-shared','-fPIC','-ffp-contract=off','-O0','-I',str(REPO/'include'),
                        str(REPO/'src/recovered/nfl2k5/player_local_postprocess.c'),'-lm','-o',str(libpath)],
                       check=True,capture_output=True)
        cls.library = ctypes.CDLL(str(libpath))
        if os.name=='nt':
            import _ctypes
            cls.addClassCleanup(_ctypes.FreeLibrary,cls.library._handle)
        cls.animation = A.AnimationSource(INDEX,INVENTORY)

    def reset_files(self):
        for entry in self.bs.entries:
            S._json(self.folder/M.body_set_file_name(entry),self.docs[entry.key])

    def compile(self, bone=None, scale=1., *, complete_derived=False):
        self.reset_files()
        intended = {}
        for entry in self.bs.entries:
            key = entry.key; ts = self.transforms[key]
            targets = S.target_positions(ts,bone,scale) if bone and key!='o3c115' else {t['name']:t['absolute'] for t in ts}
            if bone and bone.kind in ('forearm','thigh') and key!='o3c115':
                # Author the required primary witnesses independently from the
                # production target generator: endpoint scale / distal shift.
                original = {t['name']:t['absolute'] for t in ts}
                pivot = original[bone.pivot]
                if bone.kind=='forearm':
                    for name in (bone.side+'wrist',bone.side+'hand'):
                        if name in original:
                            targets[name] = tuple(a+(b-a)*scale for a,b in zip(pivot,original[name]))
                else:
                    delta = tuple((b-a)*(scale-1.) for a,b in zip(pivot,original[bone.tip]))
                    for name in (bone.side+'tibia',bone.side+'foot',bone.side+'toes'):
                        targets[name] = tuple(a+b for a,b in zip(original[name],delta))
            if key=='o3c114' and not complete_derived:
                common = {t['name'] for t in self.transforms['o3c113']}
                targets = {t['name']:targets[t['name']] if t['name'] in common else t['absolute'] for t in ts}
            doc = copy.deepcopy(self.docs[key]); author(doc,ts,targets)
            S._json(self.folder/M.body_set_file_name(entry),doc)
            intended[key] = targets
        compiled = M.compile_body_set_import(self.source,self.bs,self.folder,import_skeleton=True)
        return compiled,intended

    def test_noop_and_paired_file_refusals(self):
        self.reset_files()
        compiled = M.compile_body_set_import(self.source,self.bs,self.folder,import_skeleton=True)
        self.assertEqual(compiled.changed_bytes,0)
        for m in compiled.skeleton_plan.members:
            self.assertEqual(m.before,m.after)
        lo = self.folder/M.body_set_file_name(self.bs.entry_for('lo_body'))
        hi = self.folder/M.body_set_file_name(self.bs.entry_for('hi_body'))
        for missing in (lo,hi):
            missing.unlink()
            with self.assertRaisesRegex(M.ModelsError,S.PAIR_REASON):
                M.compile_body_set_import(self.source,self.bs,self.folder,import_skeleton=True)
            self.reset_files()
        bone = next(b for b in S.BONES if b.name=='left_forearm')
        doc = copy.deepcopy(self.docs['o3c113'])
        author(doc,self.transforms['o3c113'],S.target_positions(self.transforms['o3c113'],bone,1.05))
        S._json(lo,doc)
        with self.assertRaisesRegex(M.ModelsError,S.PAIR_REASON):
            M.compile_body_set_import(self.source,self.bs,self.folder,import_skeleton=True)

    def test_high_derived_pivots_can_be_regenerated_and_edited_head_refuses(self):
        bone = next(b for b in S.BONES if b.name=='left_forearm')
        compiled,intended = self.compile(bone,1.05)
        changed = {j['name'] for j in compiled.skeleton_plan.members[1].receipt['joints']}
        self.assertTrue({f'l_forearm_twist_{n}' for n in (25,50,75,100)} <= changed)
        self.assertTrue(compiled.report()['changed_bind_lengths'])
        self.check_compact_transport(compiled)
        self.reset_files()
        entry = self.bs.entry_for('hi_head'); doc = copy.deepcopy(self.docs[entry.key])
        joint = next(n for n in doc['nodes'] if n.get('name','').endswith(':neck'))
        joint['translation'][1] += .1
        S._json(self.folder/M.body_set_file_name(entry),doc)
        with self.assertRaisesRegex(M.ModelsError,'head/spine/neck coordination'):
            M.compile_body_set_import(self.source,self.bs,self.folder,import_skeleton=True)
        self.reset_files()
        doc = copy.deepcopy(self.docs['o3c114'])
        for n in doc['nodes']:
            if S.EXPORT_TAG in n.get('extras',{}):
                n['extras'][S.EXPORT_TAG] = 'another-export'
        S._json(self.folder/M.body_set_file_name(self.bs.entry_for('hi_body')),doc)
        with self.assertRaisesRegex(M.ModelsError,S.PAIR_REASON):
            M.compile_body_set_import(self.source,self.bs,self.folder,import_skeleton=True)

    def check_compact_transport(self, compiled):
        from nfl2k5_xiso_fixture import SyntheticXiso
        from mod_editor.core import nfl2k5_animation_import as I
        plan = compiled.skeleton_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); body = b''.join(m.before for m in plan.members)
            size = ((len(body)+5*2048+0xffff)//0x10000)*0x10000
            fixture = SyntheticXiso(root,[(0,b'x'),(1,b'x'),(2,b'x'),(0x8ee9eeed,body),(4,b'tail')],
                                    pack_sizes=(size,),pack_sectors=(64,))
            outer = A._tool('nfl_outer'); archive = outer.parse_archive(fixture.retail_packs/'0')
            members=[];at=0
            for member in plan.members:
                segments=outer.range_segments(archive.packs,[0],fixture.entry_offsets[3]+at,len(member.before))
                source={**member.source,'outer_size':len(body),'chunk_offset':at,
                        'segments':[{'pack':s.pack_name,'offset':s.pack_offset,'length':s.size} for s in segments]}
                members.append(replace(member,segments=segments,source=source));at+=len(member.before)
            compiled.skeleton_plan=replace(plan,members=tuple(members))
            output=root/'skeleton.iso'
            receipt=M.write_import_set_copy(self.source,compiled,fixture.path,output)
            expected=bytearray(fixture.image);at=fixture.virtual_to_image(fixture.entry_offsets[3])
            for member in members:
                expected[at:at+len(member.after)]=member.after;at+=len(member.after)
            self.assertEqual(output.read_bytes(),expected)
            self.assertEqual(fixture.path.read_bytes(),fixture.image)
            self.assertTrue(receipt['changed_bones'])
            self.assertEqual(M.write_import_set_copy(self.source,compiled,output,root/'again.iso')['changed_bytes'],0)
            # The unchanged head participates in the guard, not just the two
            # edited bodies: one foreign head byte must prevent publication.
            head=next(m for m in members if m.key=='o3c115')
            at=fixture.virtual_to_image(fixture.entry_offsets[3])+sum(len(m.before) for m in members[:2])+40
            with fixture.path.open('r+b') as stream:
                stream.seek(at);value=stream.read(1);stream.seek(at);stream.write(bytes([value[0]^1]))
            refused=root/'refused.iso'
            with self.assertRaises(A.AnimationError):
                M.write_import_set_copy(self.source,compiled,fixture.path,refused)
            self.assertFalse(refused.exists())
            compiled.skeleton_plan=plan

    def test_five_percent_forearm_thigh_and_generalized_native_gates(self):
        import nfl2k5_model_skeleton_validate as gate
        clip = self.animation.load('archive:3092/163')
        poses = []
        for time in (0.,.033,.5,1.,2.,clip.roots[0].duration):
            low = []
            for q in A.sample_pose(clip,time):
                axes = [A.qm.rotate(A.qm.unit(q),v) for v in ((1,0,0),(0,1,0),(0,0,1))]
                low.append([A.qm.f32(v) for row in axes for v in (*row,0.)]+[0.,0.,0.,1.])
            poses.append(low)
        evidence = []
        for bone in S.BONES:
            # Upper arms require more compression than the allocation at +5%.
            # Smaller requests remain eligible only if an exact refit succeeds.
            scale = 1.01 if bone.kind=='upper_arm' else 1.05
            with self.subTest(bone=bone.name):
                try:
                    compiled,intended = self.compile(bone,scale,complete_derived=True)
                except M.ModelsError as exc:
                    if bone.kind!='upper_arm' or 'compressed span cannot fit' not in str(exc):
                        raise
                    print(bone.name,'REFUSED:',exc,flush=True)
                    continue
                plan = compiled.skeleton_plan
                self.assertAlmostEqual(plan.receipt['changed_bones'][0]['scale'],scale,places=6)
                self.assertEqual(plan.members[2].before,plan.members[2].after)
                self.assertEqual(plan.members[3].before,plan.members[3].after)
                for m in plan.members[:2]:
                    self.assertEqual(len(m.before),len(m.after)); self.assertEqual(m.before[:32],m.after[:32])
                    self.assertGreater(m.receipt['vertices_changed'],0)
                    self.assertGreater(m.receipt['normals_changed'],0)
                report = gate.validate(self.source,plan,self.xbe,self.library,intended,poses=poses)
                print(bone.name,json.dumps(report,sort_keys=True),flush=True)
                evidence.append({'bone':bone.name,'scale':scale,**report})
        self.assertTrue({'left_forearm','left_thigh'} <= {r['bone'] for r in evidence})
        if os.environ.get('NFL2K5_SKELETON_REPORT'):
            S._json(Path(os.environ['NFL2K5_SKELETON_REPORT']),evidence)

    def test_blender_glb_forearm_and_thigh_native_positions(self):
        blender=shutil.which('blender')
        if not blender:
            self.skipTest('Optional real Blender authoring witness needs Blender on PATH')
        import nfl2k5_model_skeleton_validate as gate
        self.reset_files()
        output=Path(self.temp.name)/'blender'
        process=subprocess.run([blender,'--background','--python',
                                str(REPO/'tools/nfl2k5_model_skeleton_blender_witness.py'),'--',
                                str(self.folder),str(output)],check=True,capture_output=True,text=True,timeout=120)
        self.assertIn('H4_BLENDER_EDIT_EXPORTED thigh',process.stdout)
        common={t['name'] for t in self.transforms['o3c113']} & {t['name'] for t in self.transforms['o3c114']}
        evidence=[]
        for label in ('forearm','thigh'):
            folder=output/label
            compiled=M.compile_body_set_import(self.source,self.bs,folder,import_skeleton=True)
            intended={}
            for key in ('o3c113','o3c114'):
                file=next(folder.glob('*'+key+'.glb'))
                *_,lanes,skin=S._skin(self.source,key)
                requested=S.read_bind(M.GltfFile(file),skin.transforms,lanes.name)
                intended[key]={n:p for n,p in requested.items() if key=='o3c113' or n in common}
            result=gate.validate(self.source,compiled.skeleton_plan,self.xbe,self.library,intended,
                                 target_tolerance_cm=S.INPUT_TOLERANCE_CM)
            result['bone']='left_'+label
            self.assertAlmostEqual(compiled.skeleton_plan.receipt['changed_bones'][0]['scale'],1.05,places=5)
            print('BLENDER_GLB',label,json.dumps(result,sort_keys=True),flush=True)
            evidence.append(result)
        if os.environ.get('NFL2K5_SKELETON_REPORT'):
            S._json(Path(os.environ['NFL2K5_SKELETON_REPORT']).with_suffix('.blender.json'),evidence)


if __name__ == '__main__':
    unittest.main()
