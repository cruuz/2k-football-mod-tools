"""RMS/fit behavior with synthetic PCM; FFmpeg codec imports run without playback."""
from dataclasses import replace
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.core import audio_conform as a
from tests.mod_editor.music_fixtures import wav_bytes

class MusicConformTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.shape=a.shape_for(2,22050,128)
        self.original=struct.pack('<h',8000)*256
    def tearDown(self): self.temp.cleanup()
    def fit(self,frames=128,sample=2000,channels=2,**options):
        p=self.root/'input.wav'; p.write_bytes(wav_bytes(channels,frames,sample))
        return a.conform_music(p,self.shape,self.original,**options)

    def test_exact_wav_still_matches_rms_without_ffmpeg(self):
        with patch.object(a._convert_module(),'ffmpeg_available',return_value=False):
            pcm,r=self.fit(sample=4000)
        self.assertAlmostEqual(r.output_rms,r.original_rms,places=3)
        self.assertAlmostEqual(r.gain_db,20*math.log10(2))
        self.assertEqual(len(pcm),512)

    def test_padding_does_not_boost_content_and_trim_fades_to_zero(self):
        short,r=self.fit(frames=64,sample=4000)
        exact,e=self.fit(sample=4000)
        self.assertEqual(short[:256],exact[:256])
        self.assertEqual(short[256:],bytes(256))
        self.assertEqual(r.padded_seconds,64/22050)
        long,r=self.fit(frames=256,sample=4000)
        self.assertEqual(r.trimmed_seconds,128/22050)
        self.assertGreater(r.fade_seconds,0)
        self.assertEqual(long[-4:],bytes(4))

    def test_silent_guards_gain_cap_and_peak_ceiling(self):
        pcm,r=self.fit(sample=0)
        self.assertEqual(pcm,bytes(512)); self.assertEqual(r.gain_db,0)
        pcm,r=self.fit(sample=1)
        self.assertEqual(r.gain_db,0)
        pcm,r=self.fit(sample=100)
        self.assertTrue(r.gain_capped); self.assertAlmostEqual(r.gain_db,12)
        p=self.root/'peaky.wav'
        data=bytearray(wav_bytes(sample=2000)); struct.pack_into('<h',data,44,32767); p.write_bytes(data)
        pcm,r=a.conform_music(p,self.shape,self.original)
        self.assertTrue(r.peak_limited)
        self.assertLessEqual(max(abs(x) for x in struct.unpack('<256h',pcm)),round(32768*10**(-1/20)))
        self.assertLess(r.output_rms,r.original_rms)

    def test_stereo_mono_remix_and_cancellation(self):
        pcm=struct.pack('<4h',5000,-5000,9000,-9000)
        mono,cancellation=a.music_downmix(pcm)
        self.assertTrue(cancellation); self.assertEqual(mono,bytes(4))
        pcm,r=self.fit(channels=1,match_volume=False)
        self.assertEqual(pcm,struct.pack('<h',2000)*256)
        with self.assertRaisesRegex(ValueError,'cancelled'):
            self.fit(cancelled=lambda:True)

    def test_missing_converter_actionable_and_malformed_wav(self):
        p=self.root/'input.mp3';p.write_bytes(b'invalid')
        with patch.object(a._convert_module(),'ffmpeg_available',return_value=False):
            with self.assertRaisesRegex(ValueError,'FFmpeg.*22050 Hz PCM16'):
                a.conform_music(p,self.shape,self.original)
        p=self.root/'bad.wav';p.write_bytes(wav_bytes()[:-10])
        with self.assertRaisesRegex(ValueError,'truncated'):
            a.conform_music(p,self.shape,self.original)

    def test_converter_cancellation_reaps_the_child(self):
        import time
        module=a._convert_module()
        captured=[]
        actual=subprocess.Popen
        def spawn(*args,**kwargs):
            child=actual(*args,**kwargs);captured.append(child);return child
        start=time.monotonic()
        with patch.object(module.subprocess,'Popen',side_effect=spawn):
            with self.assertRaisesRegex(ValueError,'cancelled'):
                module._run_process([sys.executable,'-c','import time; time.sleep(10)'],
                    timeout=3,cancelled=lambda:time.monotonic()-start>.1)
        self.assertTrue(captured)
        self.assertIsNotNone(captured[0].poll())
        self.assertLess(time.monotonic()-start,3)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg/FFprobe unavailable; exact WAV fallback tested separately')
    def test_wav_mp3_flac_ogg_resample_channel_match(self):
        p=self.root/'source.wav'; p.write_bytes(wav_bytes(1,2205,1000))
        for suffix in ('wav','mp3','flac','ogg'):
            target=self.root/('converted.'+suffix)
            subprocess.run(['ffmpeg','-v','error','-i',str(p),'-ar','44100',str(target)],check=True,capture_output=True)
            pcm,r=a.conform_music(target,self.shape,self.original,match_volume=False)
            self.assertEqual(len(pcm),512)
            self.assertGreater(r.trimmed_seconds,0)
            self.assertGreater(r.source_seconds,0.09)

if __name__=='__main__': unittest.main()
