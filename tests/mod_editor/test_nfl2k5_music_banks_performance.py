"""Fast Add Songs encoding keeps every ADPCM byte and every preview sample."""
from __future__ import annotations
import math
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
import wave
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import xbox_ima_encoder as encoder
from mod_editor.core import nfl2k5_music_build as songs
from mod_editor.core.nfl2k5_ausb_fixed_slots import decode_xbox_ima_time_block


def reference(pcm, channels):
    samples = struct.unpack(f'<{len(pcm)//2}h', pcm)
    return b''.join(encoder.encode_block_scalar(samples[at+channel:at+64*channels:channels])
                    for at in range(0, len(samples), 64*channels) for channel in range(channels))


class ExactEncoderTests(unittest.TestCase):
    def test_candidates_ties_clipping_transients_and_noise(self):
        rng = random.Random(66)
        blocks = [[value]*64 for value in (0, 1, -1, 32767, -32768)]
        blocks += [[32767 if i%2 else -32768 for i in range(64)], list(range(-32, 32))]
        for n in range(80):
            blocks.append([rng.randint(-32768,32767) for _ in range(64)] if n%3 == 0 else
                          [int(23000*math.sin((i+n)*(.005+n/20))) for i in range(64)])
        for i, block in enumerate(blocks):
            with self.subTest(block=i):
                pcm = struct.pack('<64h', *block)
                actual, decoded = encoder.encode_stream_with_preview(pcm, 1)
                self.assertEqual(actual, encoder.encode_block_scalar(block))
                self.assertEqual(decoded, decode_xbox_ima_time_block(actual, 1))

    def test_stereo_channel_order_and_chunk_boundaries(self):
        samples = [int(25000*math.sin(n/17)) for n in range(64*2*5)]
        pcm = struct.pack(f'<{len(samples)}h', *samples)
        expected = reference(pcm, 2)
        encoded, preview = encoder.encode_stream_with_preview(pcm, 2)
        self.assertEqual(encoded, expected)
        self.assertEqual(preview, b''.join(decode_xbox_ima_time_block(expected[i:i+72],2)
                                          for i in range(0,len(expected),72)))
        self.assertEqual(encoder.encode_stream(pcm, 2, prefer_numpy=False), expected)

    def test_add_songs_tail_padding_uses_encoder_preview(self):
        import hashlib
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pcm = struct.pack('<130h', *[i*61-1900 for i in range(130)])
            source = root/'song.wav'
            with wave.open(str(source), 'wb') as wav:
                wav.setparams((2,2,22050,65,'NONE','not compressed'))
                wav.writeframes(pcm)
            padded = pcm+pcm[-4:]*63
            expected = reference(padded,2)
            with mock.patch.object(encoder, 'decode_stream', side_effect=AssertionError('second decode')):
                receipt = songs.encode_library_song(source, root/'song.bin', root/'preview.wav')
            self.assertEqual((root/'song.bin').read_bytes(),expected)
            decoded = b''.join(decode_xbox_ima_time_block(expected[i:i+72],2) for i in range(0,len(expected),72))
            with wave.open(str(root/'preview.wav'),'rb') as wav:
                self.assertEqual(wav.readframes(128), decoded)
            self.assertEqual(receipt['decoded_pcm_sha256'],hashlib.sha256(decoded).hexdigest())


if __name__ == '__main__':
    unittest.main()
