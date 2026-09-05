"""Portable synthetic archive tests; optional retail evidence is separate."""
from __future__ import annotations

import hashlib
from dataclasses import replace
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from nfl2k5_xiso_fixture import SyntheticXiso
from mod_editor.core import nfl2k5_music_banks as banks
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import modpack, modpack_ops


def tone(path, frames=129, channels=2):
    import math
    pcm = b''.join(struct.pack('<h', int(9000*math.sin(i*0.07))) * channels for i in range(frames))
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((channels, 2, 22050, frames, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    return path


def descriptor(name, count, channels):
    size = archive.align_up(0xB8+4*(count+1),16)
    result = bytearray(size)
    result[:4] = result[0x2C:0x30] = b'AUSB'
    struct.pack_into('<I',result,4,size-32)
    struct.pack_into('<i',result,0x30,5)
    value = name.encode('utf-16le')+b'\0\0'
    result[0x34:0x34+len(value)] = value
    value = (name+'.bin').encode('utf-16le')+b'\0\0'
    result[0x60:0x60+len(value)] = value
    struct.pack_into('<6I',result,0xA0,count,0,channels,22050,0x12000,0)
    blocks = 10 if name == 'femusic' else 1
    struct.pack_into(f'<{count+1}I',result,0xB8,*[i*36*channels*blocks for i in range(count+1)])
    return bytes(result)


def fixture(path):
    entries = [(i+1,bytes([i%251])*2048) for i in range(400)]
    pins = archive.audio.PINNED_DESCRIPTORS
    names = list(dict.fromkeys(p[4] for p in pins))
    for i,name in enumerate(names):
        channels = 1 if name == 'crib22' else 2
        count = 7 if name == 'femusic' else 59 if name in ('crib22','cribmusic') else 3
        entries[350+i] = (zlib.crc32((name+'.bin').upper().encode('utf-16le')) & 0xFFFFFFFF,
                         (b'\0'*36*channels)*count*(10 if name == 'femusic' else 1))
    for outer in {p[0] for p in pins}:
        wanted = {p[1]:p[4] for p in pins if p[0] == outer}
        pieces = []
        for i in range(max(wanted)+1):
            name = wanted.get(i)
            if name:
                count = 7 if name == 'femusic' else 59 if name in ('crib22','cribmusic') else 3
                pieces.append(descriptor(name,count,1 if name == 'crib22' else 2))
            else:
                pieces.append(b'TEST'+struct.pack('<I',16)+bytes(24)+bytes([i%251])*16)
        entries[outer] = (outer+1,b''.join(pieces))
    sizes = (65536,)*16
    sectors = tuple(64+i*32 for i in range(16))
    return SyntheticXiso(path,entries,pack_sizes=sizes,pack_sectors=sectors)


class MusicBankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.fixture = fixture(self.root)
        self.source = self.fixture.path
        self.wav = tone(self.root/'tone.wav')
        self.output = self.root/'built.iso'

    def recipe(self,count=3):
        return dict(schema=banks.SCHEMA,bank='femusic',tracks=[dict(wav=str(self.wav),title=f'Tone {i}',artist='Test') for i in range(count)])

    def test_200_tracks_count_growth_reopen_hashes_and_replay(self):
        recipe = self.recipe(200)
        planned = banks.plan(self.source,recipe)
        self.assertEqual(planned['descriptor_count'],17)
        self.assertEqual(planned['boundaries']['femusic'],[i*216 for i in range(201)])
        self.assertTrue(planned['layout']['moved_outers'])
        self.assertFalse(planned['same_count_fast_path'])
        receipt = banks.rebuild(self.source,self.output,recipe,expected_plan=planned)
        self.assertEqual(receipt['verification']['unaffected_outers'],398)
        self.assertEqual([s['index'] for s in receipt['verification']['decoded_samples']],[0,100,199])
        self.assertEqual(banks.verify(self.source,self.output,receipt)['output_sha256'],receipt['verification']['output_sha256'])
        other = self.root/'again.iso'
        replay = banks.rebuild(self.output,other,recipe)
        self.assertEqual(other.read_bytes(),self.output.read_bytes())
        self.assertTrue(replay['plan']['same_count_fast_path'])

    def test_retail_count_descriptor_stays_exact_size_and_retained_tracks(self):
        recipe = self.recipe(7)
        recipe['tracks'][0] = {'source_index':0}
        receipt = banks.rebuild(self.source,self.output,recipe)
        self.assertTrue(receipt['plan']['same_count_fast_path'])
        with archive.Disc(self.source) as old, archive.Disc(self.output) as new:
            a,b = old.banks['femusic'],new.banks['femusic']
            self.assertEqual(len(a.raw),len(b.raw))
            self.assertEqual(a.raw[:0xB8],b.raw[:0xB8])
            self.assertEqual(a.raw[0xB8+32:],b.raw[0xB8+32:])
            self.assertEqual(old.read_entry_range(old.archive_entries[a.external],0,72),
                             new.read_entry_range(new.archive_entries[b.external],0,72))

    def test_mono_input_duplicates_on_canonical_timeline(self):
        tone(self.wav,frames=65,channels=1)
        receipt = banks.rebuild(self.source,self.output,self.recipe())
        with archive.Disc(self.output) as disc:
            d = disc.banks['femusic']
            encoded = disc.read_entry_range(disc.archive_entries[d.external],0,144)
            self.assertEqual(encoded[:36],encoded[36:72])
            self.assertEqual(encoded[72:108],encoded[108:144])
        self.assertEqual(receipt['plan']['tracks'][0]['frames'],128)

    def test_shrink_keeps_physical_image_and_grow_appends_complete_f(self):
        for count in (1,200):
            with self.subTest(count=count):
                receipt = banks.rebuild(self.source,self.output,self.recipe(count),overwrite=True)
                f = receipt['plan']['layout']['packs'][-1]
                if count == 1:
                    self.assertLess(f['delta'],0)
                    self.assertEqual(self.source.stat().st_size,self.output.stat().st_size)
                else:
                    self.assertGreater(f['delta'],0)
                    self.assertEqual(self.output.stat().st_size,archive.align_up(self.source.stat().st_size)+f['size'])

    def test_plan_is_read_only_relative_paths_and_limits(self):
        recipe = self.recipe()
        for t in recipe['tracks']: t['wav'] = 'tone.wav'
        path = self.root/'library.json'
        path.write_text(json.dumps(recipe))
        before = set(self.root.iterdir())
        banks.plan(self.source,path)
        self.assertEqual(set(self.root.iterdir()),before)
        for count in (0,2,401):
            with self.assertRaises(ValueError): banks.plan(self.source,self.recipe(count))
        with patch.object(banks,'MAX_FRAMES',64):
            with self.assertRaisesRegex(ValueError,'10 minutes'): banks.plan(self.source,self.recipe())
        with patch.object(banks,'MAX_TOTAL_BYTES',10):
            with self.assertRaisesRegex(ValueError,'total'): banks.plan(self.source,self.recipe())
        with archive.Disc(self.source) as disc:
            with self.assertRaisesRegex(ValueError,'pack F'):
                archive.layout(disc,{disc.banks['femusic'].external:2**31})

    def test_bad_wave_stale_recipe_source_and_destination_refuse(self):
        planned = banks.plan(self.source,self.recipe())
        tone(self.wav,64)
        with self.assertRaisesRegex(ValueError,'stale'): banks.rebuild(self.source,self.output,self.recipe(),expected_plan=planned)
        self.assertFalse(self.output.exists())
        self.wav.write_bytes(b'not a wav')
        with self.assertRaises((ValueError,wave.Error,EOFError)): banks.plan(self.source,self.recipe())
        with self.assertRaisesRegex(ValueError,'separate copy'): banks.rebuild(self.source,self.source,self.recipe())

    def test_input_alias_destination_change_and_space_budget_refuse(self):
        with self.assertRaisesRegex(ValueError,'aliases a music source'):
            banks.rebuild(self.source,self.wav,self.recipe(),overwrite=True)
        with patch.object(banks.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
            with self.assertRaisesRegex(ValueError,'scratch space'): banks.rebuild(self.source,self.output,self.recipe())
        def change(stage,*_):
            if stage=='copy': self.output.write_bytes(b'concurrent work')
        with self.assertRaisesRegex(ValueError,'destination changed'):
            banks.rebuild(self.source,self.output,self.recipe(),progress=change)
        self.assertEqual(self.output.read_bytes(),b'concurrent work')

    def test_twin_mismatch_and_failed_second_encode_before_disc_write(self):
        with archive.Disc(self.source) as disc:
            mono=disc.banks['crib22']
            disc.banks['crib22']=replace(mono,boundaries=(0,36))
            with self.assertRaisesRegex(ValueError,'twins disagree'):
                banks._project({'bank':'cribmusic'},disc,[])
            disc.banks['crib22']=mono
            tracks=banks._tracks(self.recipe(),disc)
            planned={'tracks':tracks,'boundaries':{'cribmusic':[0,216,432,648],'crib22':[0,108,216,324]}}
            encode=banks.encode_stream
            def fail_mono(pcm,channels):
                if channels==1: raise RuntimeError('second twin failed')
                return encode(pcm,channels)
            with tempfile.TemporaryDirectory(dir=self.root) as temp:
                with patch.object(banks,'encode_stream',side_effect=fail_mono):
                    with self.assertRaisesRegex(RuntimeError,'second twin'):
                        banks._stage(disc,planned,Path(temp),lambda *_:None)
            self.assertFalse(self.output.exists())

    def test_cross_pack_stream_and_partition_relative_directory(self):
        # A larger bank spans two virtual packs. Disc partition auto-detection
        # accepts a small synthetic prefix without materialising a raw DVD.
        with patch.object(archive.audio.xiso,'XDVDFS_BASE_OFFSETS',(0,0x8000)):
            original=self.source.read_bytes()
            self.source.write_bytes(bytes(0x8000)+original)
            recipe=self.recipe(200)
            with archive.Disc(self.source) as disc:
                d=disc.banks['femusic']
                planned=banks.plan(self.source,recipe)
                self.assertEqual(disc.partition,0x8000)
            receipt=banks.rebuild(self.source,self.output,recipe)
            with archive.Disc(self.output) as disc:
                self.assertEqual(disc.partition,0x8000)
                self.assertGreater(len(disc.archive_entries[disc.banks['femusic'].external].segments),1)
                self.assertEqual(disc.nodes['F'][1],(planned['layout']['packs'][-1]['offset']-0x8000)//2048)
            self.assertEqual(self.output.read_bytes()[:0x8000],bytes(0x8000))


    def test_bad_descriptor_and_constructor_close_on_all_failures(self):
        with archive.Disc(self.source) as disc:
            d = disc.banks['femusic']
            at = disc.entry_spans(disc.archive_entries[d.outer],d.offset,4)[0].xiso_offset
        original = self.source.read_bytes()
        for off,data in ((0,b'FAIL'),(0xA0,struct.pack('<I',0xFFFFFFFF)),(0xBC,struct.pack('<I',0)),
                         (0xBC,struct.pack('<I',73)),(0xBC,struct.pack('<I',0xFFFFFFF0))):
            damaged = bytearray(original); damaged[at+off:at+off+len(data)] = data
            self.source.write_bytes(damaged)
            closed = []
            real_close = os.close
            def close(fd): closed.append(fd);real_close(fd)
            with patch.object(archive.os,'close',side_effect=close):
                with self.assertRaises(ValueError): archive.Disc(self.source)
            self.assertEqual(len(closed),1)

    def test_failed_archive_verification_source_change_and_cancel_preserve_destination(self):
        self.output.write_bytes(b'existing output')
        baseline = self.source.read_bytes()
        def fail(*_,**__): raise RuntimeError('injected failure')
        for target in ('_write_archive','verify','os.replace'):
            with patch('mod_editor.core.nfl2k5_music_banks.'+target,side_effect=fail):
                with self.assertRaisesRegex(RuntimeError,'injected'):
                    banks.rebuild(self.source,self.output,self.recipe(),overwrite=True)
            self.assertEqual(self.output.read_bytes(),b'existing output')
            self.assertEqual(self.source.read_bytes(),baseline)
            self.assertFalse(list(self.root.glob('.music-*')))
        for cancelled_stage in ('encode','archive'):
            def cancel(stage,done,total):
                if stage == cancelled_stage and (stage=='encode' or done==100): raise InterruptedError('cancelled')
            with self.assertRaises(InterruptedError):
                banks.rebuild(self.source,self.output,self.recipe(),overwrite=True,progress=cancel)
            self.assertEqual(self.output.read_bytes(),b'existing output')
        def mutate(stage,index,total):
            if stage == 'copy':
                with self.source.open('r+b') as f: f.seek(50);f.write(b'CHANGED')
        with self.assertRaisesRegex(ValueError,'source'):
            banks.rebuild(self.source,self.output,self.recipe(),overwrite=True,progress=mutate)
        self.assertEqual(self.output.read_bytes(),b'existing output')

    def test_prior_named_growth_and_unrelated_outer_edits_survive(self):
        payload=b'XBEH'+b'prior executable allocation'*9
        fd=os.open(self.source,os.O_RDWR | getattr(os,'O_BINARY',0))
        try:
            archive.write_named(fd,lambda n,at: archive.io.pread(fd,n,at),0,'default.xbe',
                                lambda n,at:payload[at:at+n],len(payload))
        finally: os.close(fd)
        with archive.Disc(self.source) as disc:
            at=disc.entry_spans(disc.archive_entries[100],0,8)[0].xiso_offset
        with self.source.open('r+b') as f: f.seek(at);f.write(b'PRIOREDIT')
        receipt=banks.rebuild(self.source,self.output,self.recipe(200))
        with archive.Disc(self.output) as disc:
            xbe=disc.entries['default.xbe']
            self.assertEqual(disc.read(xbe.size,xbe.byte_offset),payload)
            self.assertEqual(disc.read_entry_range(disc.archive_entries[100],0,9),b'PRIOREDIT')
        self.assertEqual(receipt['verification']['unrelated_files'],1)

    def test_invalid_ima_header_is_rejected_before_disc_write(self):
        with archive.Disc(self.source) as disc:
            d = disc.banks['femusic']; at = disc.entry_spans(disc.archive_entries[d.external],0,72)[0].xiso_offset
        with self.source.open('r+b') as f: f.seek(at+2);f.write(b'\xff\xff')
        recipe=self.recipe();recipe['tracks'][0]={'source_index':0}
        with self.assertRaisesRegex(ValueError,'IMA step'):
            banks.rebuild(self.source,self.output,recipe)
        self.assertFalse(self.output.exists())

    def test_corrupted_readback_track_and_unaffected_outer_fail(self):
        receipt = banks.rebuild(self.source,self.output,self.recipe())
        baseline = self.output.read_bytes()
        with archive.Disc(self.output) as disc:
            b = disc.banks['femusic']
            offsets = [disc.entry_spans(disc.archive_entries[b.external],0,1)[0].xiso_offset,
                       disc.entry_spans(disc.archive_entries[100],0,1)[0].xiso_offset]
        for at in offsets:
            damaged = bytearray(baseline);damaged[at]^=1;self.output.write_bytes(damaged)
            with self.assertRaisesRegex(ValueError,'hash differs'): banks.verify(self.source,self.output,receipt)

    def test_file_shrink_modpack_roundtrip_nested_node_and_repeat(self):
        banks.rebuild(self.source,self.output,self.recipe(1))
        pack = self.root/'music.2k5patch'
        report = modpack.export(self.source,self.output,pack,{'name':'Short music'},recipe=False,
                                 file_operations=['vc_53450030/'+n for n in archive.PACK_NAMES])
        self.assertIn(5,[op['type'] for op in report['ops']])
        out = self.root/'applied.iso'
        modpack.apply(pack,self.source,out)
        self.assertEqual(out.read_bytes(),self.output.read_bytes())
        self.assertEqual(modpack.check(pack,out)['state'],'applied')
        shrink = next(op for op in report['ops'] if op['type']==5)
        fd=os.open(self.source,os.O_RDONLY | getattr(os,'O_BINARY',0))
        try:
            bad=json.loads(json.dumps(shrink));bad['directory_offset']+=4
            view=modpack_ops.View(fd,self.source.stat().st_size,0)
            with self.assertRaisesRegex(ValueError,'directory extent'):
                modpack_ops.FileShrink.plan(bad,view,None,True)
            self.assertFalse(view.spans)
        finally: os.close(fd)
        for key,value in [('size',shrink['before']['size']),('sector',shrink['before']['sector']+1)]:
            bad=json.loads(json.dumps(shrink));bad['after'][key]=value
            with self.assertRaises(ValueError): modpack_ops.FileShrink.validate(bad,bad['before_size'],bad['payload'])


if __name__ == '__main__': unittest.main()
