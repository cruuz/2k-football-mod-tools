"""Private-evidence animation gates; each test skips precisely when its inputs are absent.

Set NFL2K5_ANIMATION_FULL_CORPUS=1 for the full native no-edit serialization gate.
All reads are read-only. Optional report output is local numerical evidence.
"""
from __future__ import annotations
import base64
from collections import Counter
import ctypes
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO),str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_animation as A
from mod_editor.core import nfl2k5_animation_math as Q
import test_nfl2k5_animation as synthetic

EXTRACTION = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'
INDEX = EXTRACTION/'vc_53450030/0'
INVENTORY = Path(os.environ.get('NFL2K5_ANIMATION_INVENTORY',str(REPO/'.scratch/resource_inventory.json')))
XBE = EXTRACTION/'default.xbe'


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not INDEX.is_file():
            raise unittest.SkipTest(f'Private retail archive index absent: {INDEX}')
        if not INVENTORY.is_file():
            raise unittest.SkipTest(f'Private resource inventory absent: {INVENTORY}; generate with tools/nfl_resource_scan.py')
        cls.source = A.AnimationSource(INDEX,INVENTORY)

    def test_catalog_covers_inventoried_roots_without_assigning_families_by_count(self):
        catalog = self.source.catalog()
        self.assertEqual(len(catalog['archive']),5198)
        self.assertEqual(Counter(row['kind'] for row in catalog['archive']),{'SMCD':4559,'MMCD':639})
        roots = [r for row in catalog['archive'] for r in row['roots']]
        self.assertEqual(len(roots),6068)
        self.assertEqual(Counter(r['rate_hz'] for r in roots),{15:6022,12:46})
        self.assertEqual(Counter(row['family'] for row in catalog['archive']),{'unknown':5196,'referee':1,'player':1})
        self.assertEqual(catalog['embedded_xbe'],[])

    def test_two_embedded_roots_pin_retail_and_preserve_absolute_pointers(self):
        if not XBE.is_file():
            self.skipTest(f'Private retail executable absent: {XBE}')
        clips = A.embedded_clips(XBE)
        self.assertEqual([c.source['header_va'] for c in clips],list(A.EMBEDDED_ROOTS))
        self.assertEqual([c.roots[0].frames for c in clips],[29,27])
        self.assertTrue(all(c.roots[0].channels==23 for c in clips))
        for clip in clips:
            sidecar = A.native_sidecar(clip)
            A.verify_sidecar(sidecar,clip)
            self.assertEqual(clip.original,base64.b64decode(sidecar['original_bytes_base64']))
            with self.assertRaises(A.AnimationError):
                A.compile_replacement(clip,A.native_rotations(clip))
            with tempfile.TemporaryDirectory() as folder:
                destination = Path(folder)/'embedded'
                A.export_clip(clip,destination)
                A.verify_sidecar(json.loads((destination/'animation.native.json').read_text()),clip)
        data = bytearray(XBE.read_bytes())
        data[-1] ^= 1
        with tempfile.TemporaryDirectory() as folder:
            foreign = Path(folder)/'foreign.xbe'
            foreign.write_bytes(data)
            with self.assertRaisesRegex(A.AnimationError,'pinned retail'):
                A.embedded_clips(foreign)

    def test_seed_hashes_skeletons_export_and_exact_known_key_edit(self):
        expected = {'archive:3107/27':('referee',46,21,'75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f'),
                    'archive:3092/163':('player',93,23,'a86c827b09db69990c4070cbb59d5c989db420a9d03427acd814823361a82e52')}
        for identity,(family,frames,channels,digest) in expected.items():
            clip = self.source.load(identity)
            self.assertEqual(A.sha256(clip.body),digest)
            self.assertEqual((clip.family,clip.roots[0].frames,clip.roots[0].channels),(family,frames,channels))
            skeleton = self.source.skeleton(clip)
            self.assertEqual(len(skeleton['bones']),25)
            self.assertEqual(len(A.project_pose(clip,.4,skeleton)),24)
            with tempfile.TemporaryDirectory() as folder:
                destination = Path(folder)/family
                A.export_clip(clip,destination,skeleton)
                A.verify_sidecar(json.loads((destination/'animation.native.json').read_text()),clip)
                replacement = A.check_key_document(clip,json.loads((destination/'animation.keys.json').read_text()))
                self.assertEqual(replacement.after,clip.original)
        ref = self.source.load('archive:3107/27')
        self.assertEqual(struct.unpack_from('<I',ref.body,0x214)[0],0x1ff80201)
        index = (0x214-ref.roots[0].rotations)//4
        frame,channel = divmod(index,21)
        keys = A.native_rotations(ref)
        keys[frame][channel] = Q.decode(0x1ff80202)
        edited = A.compile_replacement(ref,keys)
        self.assertEqual(edited.receipt['write_spans'],[{'offset':0x234,'length':1,'before_hex':'01','after_hex':'02'}])
        self.assertEqual(edited.receipt['archive_write_spans'],[{'pack':'4','offset':25875456+0x234,
                                                              'length':1,'before_hex':'01','after_hex':'02'}])

    def test_real_sampler_matches_recovered_c_at_frames_between_mirrors_loops_and_end(self):
        native = synthetic.NativeReferenceTests
        native.setUpClass()
        self.addCleanup(native.doClassCleanups)
        maximum = 0.0
        checks = 0
        for identity in ('archive:3107/27','archive:3092/163'):
            original = self.source.load(identity)
            for mode in (0,1,4,5):
                raw = bytearray(original.original)
                raw[32+original.roots[0].offset+4] = (original.roots[0].flags & ~5)|mode
                clip = A.parse_archive_span(raw,identity)
                r = clip.roots[0]
                payload = clip.body[r.rotations:r.rotations+4*r.channels*r.frames]
                storage = (ctypes.c_uint8*len(payload)).from_buffer_copy(payload)
                view = native.View(storage,len(payload),r.frames,r.channels,r.rate,r.multiplier,r.flags,r.duration)
                fun = getattr(native.lib,'vc_nfl_'+('coach_ref' if clip.family=='referee' else 'player')+'_pose_sample_title_policy')
                fun.argtypes = [ctypes.POINTER(native.View),ctypes.c_float,ctypes.c_void_p,ctypes.c_void_p]
                fun.restype = ctypes.c_int
                times = [i/(2*r.rate*r.multiplier) for i in range(2*r.frames-1)]
                times += [r.duration-.000001,r.duration,r.duration+.000001,r.duration*2+.01,100]
                for seconds in times:
                    result = (ctypes.c_float*100)()
                    self.assertEqual(fun(ctypes.byref(view),seconds,result,None),0)
                    actual = [v for q in A.sample_pose(clip,seconds) for v in q]
                    difference = max(abs(a-b) for a,b in zip(result,actual))
                    maximum = max(maximum,difference)
                    checks += 1
                    self.assertLess(difference,3e-6,(identity,mode,seconds,difference))
        print(f'Retail C pose comparisons: {checks}, maximum lane difference {maximum:.9g}',flush=True)

    @unittest.skipUnless(os.environ.get('NFL2K5_ANIMATION_FULL_CORPUS')=='1',
        'Full 14-million-word serialization gate requires NFL2K5_ANIMATION_FULL_CORPUS=1')
    def test_full_corpus_no_edit_writer_and_all_main_auxiliary_omission_choices(self):
        counts = Counter()
        for n,pair in enumerate(sorted(self.source.records)):
            clip = self.source.load(f'archive:{pair[0]}/{pair[1]}')
            if clip.kind == 'SMCD':
                result = A.compile_replacement(clip,A.native_rotations(clip))
                self.assertEqual(result.after,clip.original,clip.identity)
                self.assertEqual(result.receipt['write_spans'],[])
                counts['smcd_writer_identity'] += 1
            else:
                # No MMCD mutation API: rebuild every main word in a private buffer.
                body = bytearray(clip.body)
                for root in clip.roots:
                    for index in range(root.frames*root.channels):
                        offset = root.rotations+4*index
                        word = struct.unpack_from('<I',body,offset)[0]
                        struct.pack_into('<I',body,offset,Q.encode(Q.decode(word),word))
                self.assertEqual(clip.original[:32]+body,clip.original)
                counts['mmcd_serialization_identity'] += 1
            for root in clip.roots:
                counts['main_words'] += root.frames*root.channels
                for name,start,end in root.regions:
                    if name == 'rotations':
                        slack = clip.body[start+4*root.channels*root.frames:end]
                        counts['rotation_slack_bytes'] += len(slack)
                        counts['nonzero_rotation_slack_bytes'] += sum(v!=0 for v in slack)
                    if name == 'trajectory':
                        slack = clip.body[start+root.stride*root.frames:end]
                        counts['trajectory_slack_bytes'] += len(slack)
                        counts['nonzero_trajectory_slack_bytes'] += sum(v!=0 for v in slack)
                counts['events_strictly_after_duration'] += sum(seconds>root.duration for _,_,seconds in root.events)
                # Match the existing sampler inventory's explicit 20 us tolerance.
                counts['events_after_duration_plus_20us'] += sum(seconds>root.duration+0.00002 for _,_,seconds in root.events)
                if root.auxiliary is not None:
                    for frame in range(root.frames):
                        word = struct.unpack_from('<I',clip.body,root.auxiliary+12*frame)[0]
                        self.assertEqual(Q.encode(Q.decode(word),word),word)
                        counts['auxiliary_words'] += 1
            counts['resources'] += 1
            counts['roots'] += len(clip.roots)
            counts['body_bytes'] += len(clip.body)
            counts['whole_span_bytes'] += len(clip.original)
            if n%500 == 0:
                print(f'Corpus progress {n}/5198',flush=True)
        self.assertEqual(counts['resources'],5198)
        self.assertEqual(counts['roots'],6068)
        self.assertEqual(counts['body_bytes'],60930224)
        self.assertEqual(counts['main_words']+counts['auxiliary_words'],14091296)
        self.assertEqual(counts['rotation_slack_bytes'],31404)
        self.assertEqual(counts['nonzero_rotation_slack_bytes'],6549)
        self.assertEqual(counts['trajectory_slack_bytes'],3428)
        self.assertEqual(counts['nonzero_trajectory_slack_bytes'],2190)
        self.assertEqual(counts['events_strictly_after_duration'],143)
        self.assertEqual(counts['events_after_duration_plus_20us'],69)
        print(json.dumps(dict(counts),sort_keys=True),flush=True)
        report_path = os.environ.get('NFL2K5_ANIMATION_CORPUS_REPORT')
        if report_path:
            Path(report_path).write_text(json.dumps(dict(counts),indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
