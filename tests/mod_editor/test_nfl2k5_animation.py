"""Standalone synthetic and bounded retail animation gates."""
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
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from mod_editor.core import nfl2k5_animation as A
from mod_editor.core import nfl2k5_animation_math as Q
from animation_test_support import make_clip,simple_skeleton


class CodecTests(unittest.TestCase):
    def test_omission_sign_and_nonlargest_counterexample_survive(self):
        for word in (0x20080200,0x60080200,0xa0080200,0xe0080200,0x0319172a):
            q = Q.decode(word)
            self.assertEqual(Q.encode(q,word),word)
            self.assertEqual(Q.encode(tuple(-v for v in q),word),word)
        self.assertNotEqual(max(range(4),key=lambda i:abs(Q.decode(0x0319172a)[i])),0)

    def test_bad_rotations_refuse(self):
        for q in ((0,0,0,0),(math.nan,0,0,0),(math.inf,0,0,0),(1,2,3)):
            with self.assertRaises(ValueError):
                Q.encode(q,0x20080200)
        with self.assertRaises(ValueError):
            Q.decode(0xffffffff)

    def test_changed_key_can_change_omission_to_bound_packing_error(self):
        q = (.01,math.sqrt(.9999/2),math.sqrt(.9999/2),0)
        word = Q.encode(q,0x20080200)
        self.assertIn(word >> 30,(1,2))
        dot = min(1.,abs(sum(a*b for a,b in zip(Q.unit(q),Q.unit(Q.decode(word))))))
        self.assertLess(math.degrees(2*math.acos(dot)),.35)

    def test_no_edit_whole_span_with_nonzero_slack_and_aux(self):
        clip = make_clip()
        result = A.compile_replacement(clip,A.native_rotations(clip))
        self.assertEqual(result.after,clip.original)
        self.assertEqual(result.apply(clip.original)[0],clip.original)
        self.assertEqual(result.receipt['write_spans'],[])
        self.assertEqual(result.receipt['changed_keys'],[])
        self.assertIn(b'\x31\x41\x59\x26',result.after)

    def test_one_key_exact_receipt_and_foreign_refusal(self):
        clip = make_clip()
        keys = A.native_rotations(clip)
        offset = 32+clip.roots[0].rotations+4*clip.roots[0].channels
        word = struct.unpack_from('<I',clip.original,offset)[0]
        keys[1][0] = Q.decode(word+1)
        result = A.compile_replacement(clip,keys)
        self.assertEqual(result.receipt['changed_bytes'],1)
        self.assertEqual(result.receipt['write_spans'],[{'offset':offset,'length':1,
            'before_hex':clip.original[offset:offset+1].hex(),'after_hex':result.after[offset:offset+1].hex()}])
        self.assertEqual(result.receipt['archive_write_spans'][0]['offset'],1000+offset)
        self.assertEqual(result.status(clip.original),'original')
        self.assertEqual(result.status(result.after),'applied')
        self.assertTrue(result.apply(result.after)[1]['already_applied'])
        foreign = bytearray(clip.original)
        foreign[-1] ^= 1
        with self.assertRaisesRegex(A.AnimationError,'Mixed or foreign'):
            result.apply(bytes(foreign))
        self.assertEqual(result.before,clip.original)

    def test_receipts_split_a_word_across_pack_boundary(self):
        clip = make_clip()
        offset = 32+clip.roots[0].rotations
        clip = replace(clip,source={'segments':[{'pack':'3','offset':900,'length':offset+1},
            {'pack':'4','offset':20,'length':len(clip.original)-offset-1}]})
        keys = A.native_rotations(clip)
        keys[0][0] = Q.decode(0x20081205)
        result = A.compile_replacement(clip,keys)
        physical = result.receipt['archive_write_spans']
        self.assertEqual({s['pack'] for s in physical},{'3','4'})
        self.assertEqual(sum(s['length'] for s in physical),result.receipt['changed_bytes'])

    def test_all_fixed_fields_and_counts_refuse(self):
        clip = make_clip()
        document = A.key_document(clip)
        for key in ('identity','source_sha256','name','family','map_id','frames','channels','rate_hz',
                    'time_multiplier','duration_seconds','flags','quaternion_order','key_space','schema'):
            changed = copy.deepcopy(document)
            changed[key] = 'different'
            with self.subTest(key=key),self.assertRaises(A.AnimationError):
                A.check_key_document(clip,changed)
        for field in ('events','trajectory','new_field'):
            changed = copy.deepcopy(document)
            changed[field] = []
            with self.assertRaises(A.AnimationError):
                A.check_key_document(clip,changed)
        for keys in (document['rotations'][:-1],[row[:-1] for row in document['rotations']]):
            with self.assertRaises(A.AnimationError):
                A.compile_replacement(clip,keys)

    def test_parser_bounds_and_terminator(self):
        clip = make_clip()
        for offset,value in ((4,1),(32+clip.roots[0].offset+12,0),(32+clip.roots[0].offset+36,0)):
            raw = bytearray(clip.original)
            if offset % 4 == 0:
                struct.pack_into('<I',raw,offset,value)
            else:
                raw[offset] = value
            with self.assertRaises(ValueError):
                A.parse_archive_span(raw,clip.identity)
        raw = bytearray(clip.original)
        struct.pack_into('<I',raw,32+clip.roots[0].events_offset+8,0)
        with self.assertRaisesRegex(A.AnimationError,'terminator'):
            A.parse_archive_span(raw,clip.identity)
        with self.assertRaises(A.AnimationError):
            A.parse_archive_span(clip.original[:-1],clip.identity)

    def test_counts_do_not_establish_family_and_mmcd_writer_refuses(self):
        clip = make_clip(channels=21)
        self.assertEqual(clip.family,'unknown')
        self.assertIsNone(A.catalog_entry(clip)['bones'])
        multi = make_clip(kind='MMCD')
        self.assertEqual(len(multi.roots),2)
        self.assertEqual(multi.structure['directory_records'][0]['opaque_words_04_0c'][0],'0xdeadbeef')
        with self.assertRaisesRegex(A.AnimationError,'disabled'):
            A.compile_replacement(multi,[])
        embedded = replace(clip,kind='XBE_ROOT')
        with self.assertRaises(A.AnimationError):
            A.compile_replacement(embedded,[])

    def test_title_mirror_loop_and_end_policies(self):
        clip = make_clip(family='player',flags=5)
        root = clip.roots[0]
        self.assertEqual(A.sample_pose(clip,root.duration),A.sample_pose(clip,0))
        normal = make_clip(family='player',flags=0)
        mirrored = A.sample_pose(clip,0,complete=False)
        raw = A.sample_pose(normal,0,mapped=False)
        self.assertEqual(mirrored[1],(raw[5][0],raw[5][1],-raw[5][2],-raw[5][3]))
        end = A.sample_pose(normal,100,mapped=False)
        self.assertEqual(end,tuple(A.native_rotations(normal)[-1]))
        for seconds in (-1,float('inf'),float('nan')):
            with self.assertRaises(A.AnimationError):
                A.sample_pose(clip,seconds)

    def test_pose_comparisons_at_and_between_frames(self):
        for flags in (0,1,4,5,8,13):
            original = make_clip(family='referee',flags=flags)
            keys = A.native_rotations(original)
            keys[1][2] = Q.decode(0x20081206)
            result = A.compile_replacement(original,keys)
            edited = A.parse_archive_span(result.after,original.identity)
            for time in (0,1/15,1.5/15,original.roots[0].duration,0.8):
                expected = A.sample_pose(original,time)
                actual = A.sample_pose(edited,time)
                self.assertTrue(all(math.isfinite(v) for q in actual for v in q))
                affected = 6 if flags&4 else 2
                for i in range(25):
                    if i != affected:
                        self.assertEqual(actual[i],expected[i])
            self.assertNotEqual(A.sample_pose(original,1/15),A.sample_pose(edited,1/15))


class ExportTests(unittest.TestCase):
    def test_native_sidecar_retains_everything_and_detects_tampering(self):
        clip = make_clip(flags=8)
        document = A.native_sidecar(clip)
        A.verify_sidecar(document,clip)
        self.assertEqual(base64.b64decode(document['original_bytes_base64']),clip.original)
        self.assertGreater(document['roots'][0]['events'][1]['seconds'],clip.roots[0].duration)
        self.assertEqual(document['roots'][0]['auxiliary'][0]['shorts'][-1],-32768)
        for field in ('header_hex','omitted_lanes','trajectory','events','auxiliary'):
            bad = copy.deepcopy(document)
            bad['roots'][0][field] = None
            with self.assertRaises(A.AnimationError):
                A.verify_sidecar(bad,clip)

    def test_export_bundle_accessors_signs_hashes_and_no_edit_keys(self):
        clip = make_clip(family='referee',flags=5)
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'new export'
            result = A.export_clip(clip,destination,simple_skeleton())
            for name,digest in result['files'].items():
                self.assertEqual(A.sha256((destination/name).read_bytes()),digest)
            gltf = json.loads((destination/'animation.gltf').read_text())
            native = json.loads((destination/'animation.native.json').read_text())
            A.verify_sidecar(native,clip)
            result = A.check_key_document(clip,json.loads((destination/'animation.keys.json').read_text()))
            self.assertEqual(result.after,clip.original)
            binary = (destination/'animation.bin').read_bytes()
            self.assertEqual(len(gltf['animations'][0]['channels']),25)
            self.assertFalse(native['gltf']['root_translation_emitted'])
            for accessor in gltf['accessors']:
                view = gltf['bufferViews'][accessor['bufferView']]
                self.assertLessEqual(view['byteOffset']+view['byteLength'],len(binary))
                if accessor['type'] == 'VEC4':
                    quats = list(struct.iter_unpack('<4f',binary[view['byteOffset']:view['byteOffset']+view['byteLength']]))
                    for q in quats:
                        self.assertAlmostEqual(sum(v*v for v in q),1,places=6)
                    self.assertTrue(all(sum(x*y for x,y in zip(a,b))>=0 for a,b in zip(quats,quats[1:])))
            with self.assertRaises(A.AnimationError):
                A.export_clip(clip,destination,simple_skeleton())

    def test_mmcd_export_keeps_child_directory_and_has_no_key_edit_file(self):
        clip = make_clip(kind='MMCD')
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)/'multi'
            A.export_clip(clip,destination)
            gltf = json.loads((destination/'animation.gltf').read_text())
            self.assertEqual(len(gltf['animations']),2)
            self.assertFalse((destination/'animation.keys.json').exists())
            A.verify_sidecar(json.loads((destination/'animation.native.json').read_text()),clip)

    def test_projection_moves_and_has_no_display_dependency(self):
        clip = make_clip(family='referee')
        a = A.project_pose(clip,0,simple_skeleton())
        b = A.project_pose(clip,.1,simple_skeleton())
        self.assertEqual(len(a),24)
        self.assertNotEqual(a,b)
        self.assertEqual(len(A.project_pose(make_clip(),0)),3)


class NativeReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('cc')
        if not compiler or sys.platform == 'win32':
            raise unittest.SkipTest('Portable C comparison needs a POSIX C shared-library compiler')
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name).resolve()/'animation_reference.so'
        files = ['motion_pose_sample.c','packed_pose.c','quaternion_interpolation.c','coach_ref_pose.c','player_pose.c']
        proc = subprocess.run([compiler,'-std=c11','-shared','-fPIC','-O0','-I',str(REPO/'include'),
            *[str(REPO/'src/recovered/nfl2k5'/f) for f in files],'-lm','-o',str(path)],capture_output=True,text=True)
        if proc.returncode:
            raise AssertionError(proc.stderr)
        cls.lib = ctypes.CDLL(str(path))
        class View(ctypes.Structure):
            _fields_ = [('packed_frames',ctypes.POINTER(ctypes.c_uint8)),('packed_frame_bytes',ctypes.c_size_t),
                ('frame_count',ctypes.c_uint16),('packed_poses_per_frame',ctypes.c_uint8),('sample_rate',ctypes.c_uint8),
                ('time_scale',ctypes.c_float),('flags',ctypes.c_uint8),('duration_seconds',ctypes.c_float)]
        cls.View = View

    def test_python_sampler_and_derived_joints_against_recovered_c(self):
        maximum = 0.0
        for family in ('referee','player'):
            for flags in (0,1,4,5,8,13):
                clip = make_clip(family=family,flags=flags)
                # Exercise fixed-table interpolation, all omission lanes and
                # large joint rotations, beyond the near-identity linear path.
                raw = bytearray(clip.original)
                for frame in range(clip.roots[0].frames):
                    for channel in range(clip.roots[0].channels):
                        q = [math.sin((frame+1)*(channel+1)*(lane+1)*0.37) for lane in range(4)]
                        word = Q.encode(q,0x20080200)
                        offset = 32+clip.roots[0].rotations+4*(frame*clip.roots[0].channels+channel)
                        struct.pack_into('<I',raw,offset,word)
                clip = A.parse_archive_span(raw,clip.identity)
                r = clip.roots[0]
                payload = clip.body[r.rotations:r.rotations+4*r.channels*r.frames]
                storage = (ctypes.c_uint8*len(payload)).from_buffer_copy(payload)
                view = self.View(storage,len(payload),r.frames,r.channels,r.rate,r.multiplier,r.flags,r.duration)
                fun = getattr(self.lib,'vc_nfl_'+('coach_ref' if family=='referee' else 'player')+'_pose_sample_title_policy')
                fun.argtypes = [ctypes.POINTER(self.View),ctypes.c_float,ctypes.c_void_p,ctypes.c_void_p]
                fun.restype = ctypes.c_int
                for seconds in (0,1/15,1.5/15,r.duration-.000001,r.duration,r.duration+.000001,.8):
                    result = (ctypes.c_float*100)()
                    self.assertEqual(fun(ctypes.byref(view),seconds,result,None),0)
                    expected = A.sample_pose(clip,seconds)
                    difference = max(abs(a-b) for a,b in zip(result,[v for q in expected for v in q]))
                    maximum = max(maximum,difference)
                    self.assertLess(difference,3e-6,(family,flags,seconds,difference))
        print(f'Portable C comparison maximum lane difference: {maximum:.9g}')


if __name__ == '__main__':
    unittest.main()
