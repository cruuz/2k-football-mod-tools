"""Standalone bounded import/transaction gates; no private assets or display."""
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_animation as A, nfl2k5_animation_import as I, nfl2k5_animation_math as Q
from animation_test_support import make_clip, simple_skeleton


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)/'clip'
        self.clip = make_clip(family='referee')
        self.skeleton = simple_skeleton()
        A.export_clip(self.clip, self.folder, self.skeleton)

    def check(self):
        return I.compile_import(self.clip, self.folder/'primary.gltf', self.skeleton)

    def test_complete_no_edit_and_sign_equivalence_preserve_every_byte(self):
        self.assertEqual(self.check().replacement.after, self.clip.original)
        path = self.folder/'primary.bin'
        data = bytearray(path.read_bytes())
        r = self.clip.roots[0]
        for off in range(r.frames*4, len(data), 16):
            q = struct.unpack_from('<4f', data, off)
            struct.pack_into('<4f', data, off, *[-v for v in q])
        path.write_bytes(data)
        plan = self.check()
        self.assertEqual(plan.replacement.after, self.clip.original)
        self.assertTrue(plan.receipt['pose_preflight']['passed'])
        self.assertEqual(plan.replacement.receipt['write_spans'], [])

    def test_one_native_word_round_trips_and_every_fixed_region_stays(self):
        path = self.folder/'primary.bin'
        data = bytearray(path.read_bytes())
        r = self.clip.roots[0]
        w,x,y,z = Q.unit(Q.decode(0x20080220))
        struct.pack_into('<4f', data, r.frames*4+16*(2*r.frames+1), x,y,z,w)
        path.write_bytes(data)
        plan = self.check()
        changes = plan.replacement.receipt['changed_keys']
        self.assertEqual([(c['frame'], c['packed_channel']) for c in changes], [(1,2)])
        self.assertEqual(changes[0]['after_word'], 0x20080220)
        self.assertGreater(plan.receipt['pose_preflight']['joint_comparisons'], 100)
        lo = 32+r.rotations+4*(r.channels+2)
        self.assertEqual(plan.replacement.after[:lo], self.clip.original[:lo])
        self.assertEqual(plan.replacement.after[lo+4:], self.clip.original[lo+4:])

    def test_omission_counterexample_survives_gltf(self):
        raw = bytearray(self.clip.original)
        struct.pack_into('<I', raw, 32+self.clip.roots[0].rotations, 0x0319172a)
        c = A.parse_archive_span(raw, self.clip.identity, self.clip.source)
        folder = Path(self.temp.name)/'omission'
        A.export_clip(c,folder,self.skeleton)
        self.assertEqual(I.compile_import(c,folder/'primary.gltf',self.skeleton).replacement.after,raw)

    def test_sidecar_is_mandatory_and_source_not_self_authenticated(self):
        p = self.folder/'animation.native.json'
        original = p.read_bytes()
        p.unlink()
        with self.assertRaises(FileNotFoundError): self.check()
        p.write_bytes(original)
        d = json.loads(original);d['roots'][0]['flags'] ^= 1;p.write_text(json.dumps(d))
        with self.assertRaisesRegex(A.AnimationError,'roots'): self.check()
        p.write_bytes(original)
        raw = bytearray(self.clip.original);raw[-1] ^= 1
        with self.assertRaisesRegex(A.AnimationError,'source'):
            I.compile_import(A.parse_archive_span(raw,self.clip.identity,self.clip.source), self.folder/'primary.gltf',self.skeleton)
        with self.assertRaisesRegex(A.AnimationError,'skeleton'):
            I.compile_import(self.clip,self.folder/'primary.gltf',None)

    def test_fixed_structure_duration_frames_and_external_buffers_refuse(self):
        path = self.folder/'primary.gltf';original = path.read_bytes()
        mutations = [lambda d: d['extras'].update(duration_seconds=5),
                     lambda d: d['buffers'][0].update(uri='../outside.bin'),
                     lambda d: d['accessors'][0].update(count=90000000),
                     lambda d: d['animations'][0]['samplers'][0].update(interpolation='CUBICSPLINE'),
                     lambda d: d['nodes'][0].update(translation=[1,0,0]),
                     lambda d: d['animations'][0]['channels'].pop()]
        for mutation in mutations:
            d=json.loads(original);mutation(d);path.write_text(json.dumps(d))
            with self.assertRaises(A.AnimationError): self.check()
        path.write_bytes(original)
        binary = self.folder/'primary.bin';data=bytearray(binary.read_bytes());struct.pack_into('<f',data,4,.123)
        binary.write_bytes(data)
        with self.assertRaisesRegex(A.AnimationError,'times'): self.check()

    def test_invalid_quaternion_and_duplicate_json_fail_closed(self):
        p=self.folder/'primary.bin';original=p.read_bytes();off=self.clip.roots[0].frames*4
        for q in ((0,0,0,0),(math.nan,0,0,1),(0,0,0,2),(math.inf,0,0,0)):
            data=bytearray(original);struct.pack_into('<4f',data,off,*q);p.write_bytes(data)
            with self.assertRaises(A.AnimationError): self.check()
        p.write_bytes(original)
        p=self.folder/'primary.gltf';p.write_text('{"asset": {}, "asset": {}}')
        with self.assertRaisesRegex(A.AnimationError,'Duplicate'): self.check()

    def test_timing_beyond_duration_preserved_and_mmcd_refused(self):
        self.assertGreater((self.clip.roots[0].frames-1)/15,self.clip.roots[0].duration)
        self.assertEqual(self.check().replacement.after,self.clip.original)
        with self.assertRaisesRegex(A.AnimationError,'multi-root'):
            I.compile_import(make_clip(kind='MMCD'),self.folder/'primary.gltf')

    def test_referee_variant_keeps_endpoints_and_span(self):
        c=make_clip(family='referee',frames=12)
        p=I.author_referee_variant(c)
        a=A.native_rotations(c)
        b=A.native_rotations(A.parse_archive_span(p.replacement.after,c.identity))
        self.assertEqual(a[0],b[0]);self.assertEqual(a[-1],b[-1])
        self.assertNotEqual(a[5][14],b[5][14])
        self.assertTrue(all(x['packed_channel']==14 for x in p.replacement.receipt['changed_keys']))
        self.assertEqual(len(c.original),len(p.replacement.after))
        self.assertFalse(p.receipt['new_identity']);self.assertEqual(p.receipt['growth_bytes'],0)

    def test_pose_gate_failure_cannot_produce_an_import_plan(self):
        with patch.object(A,'sample_pose',return_value=((0.,1.,0.,0.),)*25):
            with self.assertRaisesRegex(A.AnimationError,'Decoded pose error'):self.check()


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.source=self.folder/'source';self.output=self.folder/'out'
        self.source.write_bytes(bytes(range(128)))
        self.edit=I.SpanEdit('split',bytes(range(10,14))+bytes(range(70,74)),b'ABCDE'+bytes(range(71,74)),
                             ((10,0,4),(70,4,4)))

    def test_exact_split_spans_and_unchanged_complement_receipt(self):
        before=self.source.read_bytes()
        receipt=I.write_copy(self.source,self.output,(self.edit,))
        expected=bytearray(before);expected[10:14]=b'ABCD';expected[70:74]=b'E'+bytes(range(71,74))
        self.assertEqual(self.output.read_bytes(),expected);self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual([(r['offset'],r['length']) for r in receipt['write_spans']],[(10,4),(70,1)])
        self.assertEqual(json.loads(Path(receipt['receipt_path']).read_text()),receipt)
        self.assertEqual(receipt['output_sha256'],A.sha256(expected))
        second=self.folder/'second';r=I.write_copy(self.output,second,(self.edit,))
        self.assertEqual(r['write_spans'],[]);self.assertEqual(second.read_bytes(),expected)

    def test_identity_copy_reports_zero_actual_writes(self):
        edit=replace(self.edit,after=self.edit.before)
        r=I.write_copy(self.source,self.output,(edit,))
        self.assertEqual(r['changed_bytes'],0);self.assertEqual(self.source.read_bytes(),self.output.read_bytes())

    def test_mixed_split_resource_refuses_before_output(self):
        with self.source.open('r+b') as f:f.seek(10);f.write(b'ABCD')
        with self.assertRaisesRegex(A.AnimationError,'Mixed or foreign'):
            I.write_copy(self.source,self.output,(self.edit,))
        self.assertFalse(self.output.exists())

    def test_overlapping_missing_and_out_of_bounds_mapping_refuse(self):
        for spans in (((10,0,4),(12,4,4)),((10,0,4),),((10,1,4),(70,4,4)),((127,0,8),)):
            with self.assertRaises(A.AnimationError):I.write_copy(self.source,self.output,(replace(self.edit,spans=spans),))
        self.assertFalse(self.output.exists())

    def test_foreign_late_member_preflights_before_any_write(self):
        other=I.SpanEdit('foreign',b'bad',b'new',((90,0,3),))
        with patch.object(I.io,'pwrite',side_effect=AssertionError('must not write')):
            with self.assertRaises(A.AnimationError):I.write_copy(self.source,self.output,(self.edit,other))
        self.assertFalse(self.output.exists())

    def test_partial_write_readback_and_publish_failure_leave_no_output(self):
        for failing in ('write','readback','replace'):
            with self.subTest(failing=failing):
                if failing=='replace':ctx=patch.object(I.os,'replace',side_effect=OSError('simulated publish failure'))
                elif failing=='write':ctx=patch.object(I.io,'pwrite',return_value=0)
                else:ctx=patch.object(I.io,'pwrite',side_effect=lambda fd,data,off:len(data))
                with ctx:
                    with self.assertRaises((A.AnimationError,OSError)):I.write_copy(self.source,self.output,(self.edit,))
                self.assertFalse(self.output.exists());self.assertEqual(sorted(p.name for p in self.folder.iterdir()),['source'])

    def test_same_existing_hardlink_and_receipt_targets_refuse(self):
        with self.assertRaises(A.AnimationError):I.write_copy(self.source,self.source,(self.edit,))
        os.link(self.source,self.output)
        with self.assertRaises(A.AnimationError):I.write_copy(self.source,self.output,(self.edit,))
        self.output.unlink()
        self.output.with_name('out.animation-receipt.json').write_text('existing')
        with self.assertRaises(A.AnimationError):I.write_copy(self.source,self.output,(self.edit,))
        self.assertFalse(self.output.exists())

    def test_source_changes_during_copy_refuses_and_cleans_stage(self):
        def progress(*_):
            with self.source.open('r+b') as f:f.seek(100);f.write(b'x')
        with self.assertRaisesRegex(A.AnimationError,'Source changed'):
            I.write_copy(self.source,self.output,(self.edit,),progress=progress)
        self.assertFalse(self.output.exists())

    def test_all_streams_and_raw_descriptors_close_before_publication(self):
        from test_modpack import windows_file_locks
        streams=[];opened=Path.open;replace_file=os.replace
        def track(path,*args,**kwargs):
            stream=opened(path,*args,**kwargs);streams.append(stream);return stream
        def publish(source,target):
            self.assertTrue(all(stream.closed for stream in streams))
            return replace_file(source,target)
        with windows_file_locks() as handles,patch.object(Path,'open',track),patch.object(os,'replace',publish):
            I.write_copy(self.source,self.output,(self.edit,))
            self.assertEqual(handles(),[])


if __name__=='__main__':unittest.main()
