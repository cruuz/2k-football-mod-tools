"""Synthetic alias rejection and PCM16 quantization, with no audio playback."""
import array
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import audio_conform as shared
from mod_editor.core import nfl2k5_music_conform as music


def energy_db(values):
    return 10*math.log10(max(1e-300, sum(v*v for v in values)/len(values)))


def float_wav(path, start, end, rate=48000, seconds=2):
    n = rate*seconds
    # Float64 avoids measuring PCM16 source quantization noise as filter alias.
    samples = array.array('d', (.75*math.sin(2*math.pi*(start*(i/rate)+
        (end-start)/(2*seconds)*(i/rate)**2)) for i in range(n)))
    if sys.byteorder != 'little': samples.byteswap()
    pcm = samples.tobytes()
    fmt = struct.pack('<HHIIHH', 3, 1, rate, rate*8, 8, 64)
    path.write_bytes(b'RIFF'+struct.pack('<I',36+len(pcm))+b'WAVEfmt '+
                    struct.pack('<I',16)+fmt+b'data'+struct.pack('<I',len(pcm))+pcm)


class QuantizerTests(unittest.TestCase):
    def test_tpdf_removes_sub_lsb_dc_bias_and_is_chunk_stable(self):
        samples = [.25/32768]*100000
        old = shared._pcm_samples(shared._convert_module()._quantize(samples))
        quantize = music.TPDFQuantizer()
        pcm = quantize(samples[:32768])+quantize(samples[32768:])
        self.assertEqual(pcm, music.TPDFQuantizer()(samples))
        new = shared._pcm_samples(pcm)
        mean = sum(new)/len(new)
        self.assertAlmostEqual(mean, .25, delta=.005)
        self.assertEqual(sum(old), 0)
        self.assertEqual(set(new), {-1, 0, 1})
        variance = sum((v-.25)**2 for v in new)/len(new)
        self.assertAlmostEqual(variance, .25, delta=.006)
        print(json.dumps(dict(tpdf_mean_lsb=mean, old_mean_lsb=0,
                              target_mean_lsb=.25, tpdf_error_variance_lsb2=variance)))

    def test_silence_rails_nonfinite_and_independent_channel_noise(self):
        self.assertEqual(music.TPDFQuantizer()([0.0]*100), bytes(200))
        values = shared._pcm_samples(music.TPDFQuantizer()([2.0, -2.0]*100))
        self.assertEqual(list(values), [32767, -32768]*100)
        pairs = shared._pcm_samples(music.TPDFQuantizer()([.25/32768]*1000))
        self.assertNotEqual(list(pairs[::2]), list(pairs[1::2]))
        for value in (float('nan'), float('inf')):
            with self.assertRaisesRegex(ValueError, 'damaged'):
                music.TPDFQuantizer()([value])


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg/FFprobe required for measured music resample')
class FilterTests(unittest.TestCase):
    def test_out_of_band_sweep_rejects_alias_energy_and_passband_stays_level(self):
        module = shared._convert_module()
        shape = shared.shape_for(1, 22050, 44100)
        metrics = {}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'sweep.wav'
            for name, start, end in (('stopband',11026,20000), ('passband',100,8000)):
                float_wav(path, start, end)
                source = module.probe(path)
                old = array.array('f', module._decode(source, shape, 30))
                new = array.array('f', music.decode_music(source, shape, 30))
                if sys.byteorder != 'little': old.byteswap(); new.byteswap()
                self.assertEqual(len(new), len(old))
                # Exclude 100 ms at both edges. For the wholly out-of-band
                # sweep all residual output is alias/error, before dither.
                metrics[name] = dict(old_dbfs=energy_db(old[2205:-2205]),
                                     new_dbfs=energy_db(new[2205:-2205]))
            rejection = metrics['stopband']['old_dbfs']-metrics['stopband']['new_dbfs']
            self.assertGreater(rejection, 6)
            self.assertLess(abs(metrics['passband']['old_dbfs']-metrics['passband']['new_dbfs']), .01)
            self.assertLess(metrics['stopband']['new_dbfs'], -150)
            metrics['improvement_db'] = rejection
            print(json.dumps(metrics, sort_keys=True))

    def test_both_import_paths_resample_fit_and_are_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'sweep.wav'
            float_wav(source, 200, 8000)
            a, b = Path(tmp)/'a.wav', Path(tmp)/'b.wav'
            first = music.conform_song(source, a, reference_rms=.2)
            second = music.conform_song(source, b, reference_rms=.2)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(first, second)
            with wave.open(str(a)) as wav:
                self.assertEqual((wav.getframerate(),wav.getsampwidth(),wav.getnchannels()), (22050,2,2))
                self.assertEqual(wav.getnframes(),44100)
            shape = shared.shape_for(2,22050,22050)
            original = struct.pack('<h',4000)*44100
            pcm, report = music.conform_music(source,shape,original)
            self.assertEqual(len(pcm),shape.pcm_bytes)
            self.assertGreater(report.trimmed_seconds,0)
            self.assertEqual(pcm[-4:], bytes(4))
            with self.assertRaisesRegex(ValueError,'cancelled'):
                music.conform_song(source,b,reference_rms=.2,cancelled=lambda:True)


if __name__ == '__main__':
    unittest.main()
