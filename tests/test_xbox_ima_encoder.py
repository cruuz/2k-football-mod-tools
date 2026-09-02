"""The Xbox IMA encoder must agree with three things already in this tree.

NFL 2K5 stores every one of its 850 standalone AUDO records as Xbox IMA ADPCM,
so this encoder is what stands between a modder's audio and the game.  There is
no room for "close enough": the shipped decoder, the established reference
encoder, and this module's own two code paths all have to produce identical
bytes, or a slot is written with audio nobody verified.

The vectorised path exists because the exhaustive search it preserves is worth
about 3 dB over a cheaper windowed one, while costing ~110 s for a 30-second
sound in scalar Python.  Vectorising across candidate start indices *and* across
blocks brings that to a few seconds without changing a single output byte -- so
the tests that matter most here assert byte equality, not similarity.
"""

from __future__ import annotations

import math
from pathlib import Path
import random
import struct
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import xbox_ima_encoder as encoder  # noqa: E402


def _blocks(count: int, seed: int = 4242) -> list[tuple[int, ...]]:
    """Material chosen to stress the parts where a tie-break could diverge."""

    rng = random.Random(seed)
    out: list[tuple[int, ...]] = [
        tuple([0] * 64),
        tuple([32767] * 64),
        tuple([-32768] * 64),
        tuple(range(-32768, -32768 + 64)),
        tuple(range(32767, 32767 - 64, -1)),
    ]
    while len(out) < count:
        kind = rng.choice(("noise", "near", "tone", "quiet", "step"))
        if kind == "noise":
            out.append(tuple(rng.randint(-32768, 32767) for _ in range(64)))
        elif kind == "near":
            base = rng.randint(-20000, 20000)
            out.append(tuple(
                max(-32768, min(32767, base + rng.randint(-400, 400)))
                for _ in range(64)
            ))
        elif kind == "tone":
            frequency = rng.uniform(30, 9000)
            amplitude = rng.uniform(0.002, 1.0)
            phase = rng.uniform(0, 6.283)
            out.append(tuple(
                int(max(-1.0, min(1.0, amplitude * math.sin(
                    2 * math.pi * frequency * n / 22050 + phase))) * 32767)
                for n in range(64)
            ))
        elif kind == "quiet":
            out.append(tuple(rng.randint(-12, 12) for _ in range(64)))
        else:
            edge = rng.randint(1, 62)
            high, low = rng.randint(0, 32767), rng.randint(-32768, 0)
            out.append(tuple(high if n < edge else low for n in range(64)))
    return out


def _pcm(samples) -> bytes:
    return struct.pack(f"<{len(samples)}h", *samples)


class BlockContractTests(unittest.TestCase):
    def test_a_block_is_thirty_six_bytes_per_channel(self) -> None:
        self.assertEqual(encoder.CHANNEL_BLOCK_BYTES, 36)
        self.assertEqual(encoder.BLOCK_FRAMES, 64)
        self.assertEqual(encoder.block_align(1), 36)
        self.assertEqual(encoder.block_align(2), 72)

    def test_sizes_round_trip(self) -> None:
        for channels in (1, 2):
            for frames in (64, 640, 10624, 370624):
                size = encoder.encoded_size(frames, channels)
                self.assertEqual(size % encoder.block_align(channels), 0)
                self.assertEqual(
                    encoder.frames_for_payload(size, channels), frames
                )

    def test_shapes_that_cannot_be_encoded_are_refused(self) -> None:
        for channels in (0, 3, 8):
            with self.subTest(channels=channels):
                with self.assertRaises(encoder.XboxImaEncodeError):
                    encoder.block_align(channels)
        with self.assertRaises(encoder.XboxImaEncodeError):
            encoder.encoded_size(65, 1)          # not a whole block
        with self.assertRaises(encoder.XboxImaEncodeError):
            encoder.encode_stream(_pcm([0] * 63), 1)
        with self.assertRaises(encoder.XboxImaEncodeError):
            encoder.encode_stream(b"", 1)
        with self.assertRaises(encoder.XboxImaEncodeError):
            encoder.encode_stream(_pcm([0] * 64), 2)   # odd frame split


class AgreesWithTheReferenceEncoderTests(unittest.TestCase):
    """The established encoder is the authority; this one must match it."""

    @classmethod
    def setUpClass(cls) -> None:
        import nfl_audo_wav_xiso_workflow as reference

        cls.reference = reference
        cls.blocks = _blocks(320)

    def test_every_block_encodes_identically(self) -> None:
        for index, block in enumerate(self.blocks):
            with self.subTest(block=index):
                self.assertEqual(
                    encoder.encode_block_scalar(block),
                    self.reference.encode_block(block),
                )

    def test_a_whole_mono_stream_matches_block_by_block_encoding(self) -> None:
        flat = [value for block in self.blocks for value in block]
        expected = b"".join(self.reference.encode_block(b) for b in self.blocks)
        self.assertEqual(encoder.encode_stream(_pcm(flat), 1), expected)


class VectorisedMatchesScalarTests(unittest.TestCase):
    """A faster path that changes the bytes is not a faster path."""

    @classmethod
    def setUpClass(cls) -> None:
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover - exercised on lean hosts
            raise unittest.SkipTest("NumPy is not installed")
        cls.blocks = _blocks(260, seed=99)

    def test_mono_paths_agree(self) -> None:
        flat = [value for block in self.blocks for value in block]
        payload = _pcm(flat)
        self.assertEqual(
            encoder.encode_stream(payload, 1, prefer_numpy=True),
            encoder.encode_stream(payload, 1, prefer_numpy=False),
        )

    def test_stereo_paths_agree_and_channels_do_not_bleed(self) -> None:
        left = _blocks(120, seed=1)
        right = _blocks(120, seed=2)
        left_flat = [v for block in left for v in block]
        right_flat = [v for block in right for v in block]
        interleaved: list[int] = []
        for position in range(len(left_flat)):
            interleaved.append(left_flat[position])
            interleaved.append(right_flat[position])
        payload = _pcm(interleaved)

        fast = encoder.encode_stream(payload, 2, prefer_numpy=True)
        slow = encoder.encode_stream(payload, 2, prefer_numpy=False)
        self.assertEqual(fast, slow)

        # Channel-major within a time block: channel 1 begins at +0x24, which is
        # NOT FFmpeg's interleaved-nibble layout and is the reason a stock IMA
        # encoder cannot be substituted here.
        self.assertEqual(fast[:36], encoder.encode_block_scalar(tuple(left_flat[:64])))
        self.assertEqual(fast[36:72], encoder.encode_block_scalar(tuple(right_flat[:64])))


class AgreesWithTheShippedDecoderTests(unittest.TestCase):
    """What the editor reads back has to be what this module thinks it wrote."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_audio_source_scan

        cls.scan = nfl2k5_audio_source_scan

    def test_mono_and_stereo_decode_identically(self) -> None:
        for channels in (1, 2):
            with self.subTest(channels=channels):
                blocks = _blocks(40, seed=7 + channels)
                flat = [v for block in blocks for v in block]
                frames = (len(flat) // channels) // 64 * 64
                trimmed = flat[: frames * channels]
                payload = encoder.encode_stream(_pcm(trimmed), channels)
                self.assertEqual(
                    encoder.decode_stream(payload, channels),
                    self.scan.decode_xbox_ima_batch(payload, channels),
                )


class QualityTests(unittest.TestCase):
    """The exhaustive search is the reason to keep this encoder; hold its floor."""

    def test_a_tone_survives_the_round_trip_well(self) -> None:
        frames = 22016  # 344 whole blocks; a slot is always a whole number
        signal = [
            int(32767 * 0.55 * math.sin(2 * math.pi * 330 * n / 22050)
                * (0.4 + 0.6 * math.sin(2 * math.pi * 1.3 * n / 22050)))
            for n in range(frames)
        ]
        payload = encoder.encode_stream(_pcm(signal), 1)
        decoded = struct.unpack(f"<{frames}h", encoder.decode_stream(payload, 1))

        error = sum((a - b) ** 2 for a, b in zip(signal, decoded))
        energy = sum(value * value for value in signal)
        snr = 10 * math.log10(energy / error)

        # Measured across all 849 real slots the median is ~32.5 dB and the
        # minimum ~32.3 dB. Typical IMA implementations land nearer 20-25 dB;
        # a regression below 28 means the start-index search has been weakened.
        self.assertGreater(snr, 28.0)

    def test_silence_encodes_and_decodes_exactly(self) -> None:
        payload = encoder.encode_stream(_pcm([0] * 640), 1)
        decoded = encoder.decode_stream(payload, 1)
        self.assertEqual(decoded, _pcm([0] * 640))

    def test_the_first_frame_of_every_block_is_stored_exactly(self) -> None:
        """The predictor is verbatim, so block starts must be lossless."""

        blocks = _blocks(24, seed=555)
        flat = [v for block in blocks for v in block]
        payload = encoder.encode_stream(_pcm(flat), 1)
        decoded = struct.unpack(f"<{len(flat)}h", encoder.decode_stream(payload, 1))
        for start in range(0, len(flat), 64):
            self.assertEqual(flat[start], decoded[start])


if __name__ == "__main__":
    unittest.main()
