"""Synthetic XDVDFS banks: copy/readback, seams, transactional failures, format 2."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.music_fixtures import MusicDisc,music_session,wav_bytes,cs
from mod_editor.core.nfl2k5_music_build import build_copy,export_patch
from mod_editor.core import modpack

class MusicBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.disc=MusicDisc(self.root)
        service,_=music_session(self.root,self.disc)
        wav=self.root/'authored.wav';wav.write_bytes(wav_bytes(sample=3333))
        service.replace_batch([('cribmusic:28',wav)],match_volume=False)
        self.edits=service.encoded_edits()
        self.before=self.disc.path.read_bytes()
    def tearDown(self): self.temp.cleanup()
    def build(self,source=None,name='out.iso',edits=None,**kwargs):
        out=self.root/name
        receipt=build_copy(source or self.disc.path,out,self.edits if edits is None else edits,
                           descriptors=self.disc.descriptors,**kwargs)
        return out,receipt

    def test_exact_spans_seam_preserve_every_other_byte_and_repeat_does_not_grow(self):
        output,r=self.build()
        after=output.read_bytes();expected=bytearray(self.before)
        with cs.DiscBanks(self.disc.path,descriptors=self.disc.descriptors) as disc:
            self.assertEqual(len(disc.stream_by_id('crib22:28').spans),2)
            for edit in self.edits:
                stream=disc.stream_by_id(edit.stream_id);cursor=0;payload=edit.encoded_path.read_bytes()
                for span in stream.spans:
                    expected[span.xiso_offset:span.xiso_offset+span.length]=payload[cursor:cursor+span.length]
                    cursor+=span.length
        self.assertEqual(after,expected)
        self.assertEqual(self.disc.path.read_bytes(),self.before)
        self.assertFalse(r['layout_changed']);self.assertFalse(r['already_applied'])
        repeat,second=self.build(output,name='repeat.iso')
        self.assertEqual(repeat.read_bytes(),after);self.assertTrue(second['already_applied'])
        self.assertEqual(r['source_size'],r['result_size'])

    def test_failed_second_twin_wrong_length_invalid_ima_and_missing_pair_never_publish(self):
        bad=self.root/'bad.bin';bad.write_bytes(self.edits[1].encoded_path.read_bytes()[:-1])
        variants=(self.edits[:1],
                  (self.edits[0],replace(self.edits[1],expected_sha256='0'*64)),
                  (self.edits[0],replace(self.edits[1],encoded_path=bad)))
        for i,edits in enumerate(variants):
            with self.assertRaises(ValueError): self.build(name=f'bad{i}.iso',edits=edits)
            self.assertFalse((self.root/f'bad{i}.iso').exists())
        payload=bytearray(self.edits[1].encoded_path.read_bytes());payload[2]=89;bad.write_bytes(payload)
        edits=(self.edits[0],replace(self.edits[1],encoded_path=bad,encoded_sha256=hashlib.sha256(payload).hexdigest()))
        with self.assertRaises(ValueError):self.build(edits=edits)
        self.assertFalse((self.root/'out.iso').exists())
        self.assertEqual(self.disc.path.read_bytes(),self.before)

    def test_mixed_and_foreign_sources_refuse(self):
        output,r=self.build()
        with cs.DiscBanks(output,writable=True,descriptors=self.disc.descriptors) as disc:
            stream=disc.stream_by_id('crib22:28')
            for part in stream.spans:
                cs._pwrite_exact(disc.descriptor,self.before[part.xiso_offset:part.xiso_offset+part.length],part.xiso_offset)
        with self.assertRaisesRegex(ValueError,'Mixed'):self.build(output,name='mixed.iso')
        self.assertFalse((self.root/'mixed.iso').exists())

    def test_cancellation_publication_failure_and_source_change_remove_stage(self):
        with self.assertRaisesRegex(ValueError,'cancelled'):self.build(cancelled=lambda:True)
        with patch('mod_editor.core.nfl2k5_music_build.platform_compat.publish_no_replace',side_effect=OSError('publish failed')):
            with self.assertRaisesRegex(OSError,'publish failed'):self.build()
        changed=False
        def mutate(stage,done,total):
            nonlocal changed
            if stage=='Copy music image' and not changed:
                changed=True
                with self.disc.path.open('r+b') as f:f.seek(36*2048);f.write(b'changed')
        with self.assertRaisesRegex(ValueError,'Source changed'):self.build(progress=mutate)
        self.assertFalse((self.root/'out.iso').exists())
        self.assertFalse(list(self.root.glob('.music-build-*')))

    def test_source_aliases_existing_outputs_and_constructor_failures_release_handles(self):
        with self.assertRaises(ValueError):self.build(name='music.iso')
        alias=self.root/'alias.iso';os.link(self.disc.path,alias)
        with self.assertRaises(ValueError):self.build(name='alias.iso')
        opened=[];actual=os.open
        def capture(*args,**kwargs):
            fd=actual(*args,**kwargs);opened.append(fd);return fd
        with patch.object(cs.os,'open',side_effect=capture):
            with self.assertRaises(ValueError):
                cs.DiscBanks(self.disc.path,descriptors=((999999,0,0,192,'femusic'),))
        for fd in opened:
            with self.assertRaises(OSError):os.fstat(fd)

    def test_format2_authored_payload_roundtrip_repeat_and_wrong_base(self):
        output,r=self.build();pack=self.root/'music.2k5patch'
        result=export_patch(self.disc.path,output,pack,self.edits,descriptors=self.disc.descriptors)
        self.assertEqual(result['format'],2);self.assertEqual(result['min_reader_version'],2)
        self.assertTrue(result['recipe_lines'][0].startswith('Replace 1 music slot;'))
        self.assertNotIn('sha256',result['recipe_lines'][0])
        with zipfile.ZipFile(pack) as archive:
            payload=archive.read('operations/music.bin')
            self.assertEqual(len(payload),sum(len(e.encoded_path.read_bytes()) for e in self.edits))
            self.assertEqual(payload,self.edits[1].encoded_path.read_bytes()+self.edits[0].encoded_path.read_bytes())
            self.assertFalse(any(n.startswith('original') for n in archive.namelist()))
        applied=self.root/'applied.iso';modpack.apply(pack,self.disc.path,applied)
        self.assertEqual(applied.read_bytes(),output.read_bytes())
        self.assertEqual(modpack.check(pack,applied)['state'],'applied')
        foreign=self.root/'foreign.iso';shutil.copyfile(self.disc.path,foreign)
        with cs.DiscBanks(foreign,writable=True,descriptors=self.disc.descriptors) as disc:
            at=disc.stream_by_id('crib22:28').spans[0].xiso_offset
            cs._pwrite_exact(disc.descriptor,b'bad',at)
        with self.assertRaises(ValueError):modpack.apply(pack,foreign,self.root/'refused.iso')
        self.assertFalse((self.root/'refused.iso').exists())

    def test_raw_partition_offsets_roundtrip(self):
        raw=self.root/'raw.iso'
        partition=0x02080000
        with raw.open('wb') as f:
            f.seek(partition);f.write(self.before)
        output,r=self.build(raw,name='raw-out.iso')
        pack=self.root/'raw.2k5patch'
        result=export_patch(raw,output,pack,self.edits,descriptors=self.disc.descriptors)
        self.assertEqual(result['base']['partition_base'],partition)
        applied=self.root/'raw-applied.iso'
        modpack.apply(pack,raw,applied)
        self.assertEqual(modpack.hash_file(applied),modpack.hash_file(output))
        with output.open('rb') as f:
            self.assertEqual(f.read(partition),bytes(partition))

    def test_other_staged_changes_preserved_and_undeclared_export_changes_refused(self):
        stage=self.root/'staged.iso';shutil.copyfile(self.disc.path,stage)
        with stage.open('r+b') as f:f.seek(36*2048);f.write(b'unrelated roster marker')
        output,r=self.build(stage)
        self.assertEqual(output.read_bytes()[36*2048:36*2048+23],b'unrelated roster marker')
        with self.assertRaisesRegex(ValueError,'outside the declared'):
            export_patch(self.disc.path,output,self.root/'bad.2k5patch',self.edits,descriptors=self.disc.descriptors)
        self.assertFalse((self.root/'bad.2k5patch').exists())

if __name__=='__main__':unittest.main()
