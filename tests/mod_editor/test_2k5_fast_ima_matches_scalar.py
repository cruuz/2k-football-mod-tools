"""The fast Xbox IMA path must be a speed change and nothing else.

The editor encodes every 2K5 audio replacement with an exhaustive search: each
64-frame block tries all 89 candidate start indices and keeps the lowest-error
one.  That search is worth roughly 3 dB and is deliberately kept, but in scalar
Python it costs about 11 ms per block -- the largest slot in the corpus is
370,624 frames of stereo, which is around two minutes of the editor sitting
still.

The vectorised path removes that wait by stepping all candidates and all blocks
together.  It is only safe because it is *byte-identical*: a "faster" encoder
that produced merely-similar audio would silently change every slot a modder
writes, and no amount of measured SNR would make that acceptable.  So these
tests compare bytes, on the real shapes the game actually uses, including the
stereo layout where a channel mix-up would be easy to miss.
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import sys
import time
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_audo_fixed_slots as fixed  # noqa: E402


def _scalar_encode(wav: fixed.StrictWav, slot: fixed.FixedAudoSlot) -> bytes:
    """The reference loop, reproduced so the fast path cannot shadow it."""

    chunks: list[bytes] = []
    for first_frame in range(0, slot.frame_count, fixed.BLOCK_FRAMES):
        base = first_frame * slot.channels
        for channel in range(slot.channels):
            samples = tuple(
                wav.samples[base + frame * slot.channels + channel]
                for frame in range(fixed.BLOCK_FRAMES)
            )
            chunks.append(fixed._encode_channel_block(samples))
    return b"".join(chunks)


def _signal(frames: int, channels: int, kind: str) -> tuple[int, ...]:
    values: list[int] = []
    level = 0.0
    for n in range(frames):
        if kind == "tonal":
            base = (0.45 * math.sin(2 * math.pi * 220 * n / 22050)
                    + 0.25 * math.sin(2 * math.pi * 661 * n / 22050))
        elif kind == "transient":
            if n % 1500 == 0:
                level = 1.0
            level *= 0.9992
            base = level * math.sin(2 * math.pi * 380 * n / 22050)
        elif kind == "silence":
            base = 0.0
        else:  # rails
            base = 1.0 if (n // 40) % 2 == 0 else -1.0
        for channel in range(channels):
            scale = 1.0 if channel == 0 else 0.62
            values.append(int(max(-1.0, min(1.0, base * scale)) * 30000))
    return tuple(values)


def _wav(frames: int, channels: int, rate: int, kind: str) -> fixed.StrictWav:
    import hashlib

    samples = _signal(frames, channels, kind)
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    return fixed.StrictWav(
        channels=channels,
        sample_rate=rate,
        frame_count=frames,
        samples=samples,
        pcm_sha256=hashlib.sha256(pcm).hexdigest(),
    )


class _Slot:
    """Minimal stand-in carrying only what the encoder reads."""

    def __init__(self, channels: int, sample_rate: int, frame_count: int) -> None:
        self.channels = channels
        self.sample_rate = sample_rate
        self.frame_count = frame_count
        self.payload_size = (
            frame_count // fixed.BLOCK_FRAMES
            * fixed.CHANNEL_BLOCK_BYTES
            * channels
        )


class FastPathIsByteIdenticalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            import numpy  # noqa: F401
        except ImportError:  # pragma: no cover - exercised on lean hosts
            raise unittest.SkipTest("NumPy is not installed")

    def test_it_matches_on_every_shape_and_signal(self) -> None:
        # Rates drawn from the shapes the real corpus actually carries.
        for channels in (1, 2):
            for rate in (11025, 22050, 16000):
                for kind in ("tonal", "transient", "silence", "rails"):
                    with self.subTest(channels=channels, rate=rate, signal=kind):
                        slot = _Slot(channels, rate, 640)
                        wav = _wav(640, channels, rate, kind)
                        self.assertEqual(
                            fixed.encode_xbox_ima(wav, slot),
                            _scalar_encode(wav, slot),
                        )

    def test_stereo_channels_stay_in_their_own_sub_blocks(self) -> None:
        """Channel 1 begins at +0x24, not interleaved nibbles."""

        slot = _Slot(2, 22050, 128)
        wav = _wav(128, 2, 22050, "tonal")
        payload = fixed.encode_xbox_ima(wav, slot)

        left = tuple(wav.samples[0:128 * 2:2][:64])
        right = tuple(wav.samples[1:128 * 2:2][:64])
        self.assertEqual(payload[:36], fixed._encode_channel_block(left))
        self.assertEqual(payload[36:72], fixed._encode_channel_block(right))

    def test_the_fast_path_is_actually_being_taken(self) -> None:
        """A silent fallback would make the equality tests meaningless."""

        slot = _Slot(1, 22050, 640)
        wav = _wav(640, 1, 22050, "tonal")
        self.assertIsNotNone(fixed._encode_vectorised(wav, slot))

    def test_absent_numpy_falls_back_rather_than_failing(self) -> None:
        import builtins

        real_import = builtins.__import__

        def refuse_numpy(name, *args, **kwargs):
            if name == "numpy":
                raise ImportError("numpy disabled for this test")
            return real_import(name, *args, **kwargs)

        slot = _Slot(1, 22050, 320)
        wav = _wav(320, 1, 22050, "tonal")
        builtins.__import__ = refuse_numpy
        try:
            self.assertIsNone(fixed._encode_vectorised(wav, slot))
            without = fixed.encode_xbox_ima(wav, slot)
        finally:
            builtins.__import__ = real_import
        self.assertEqual(without, _scalar_encode(wav, slot))

    def test_it_is_materially_faster_on_a_realistic_slot(self) -> None:
        """The whole point; a fast path that is not fast is dead weight."""

        frames = 6400  # 100 blocks, well short of the corpus maximum
        slot = _Slot(1, 22050, frames)
        wav = _wav(frames, 1, 22050, "transient")

        started = time.perf_counter()
        fast = fixed.encode_xbox_ima(wav, slot)
        fast_seconds = time.perf_counter() - started

        started = time.perf_counter()
        slow = _scalar_encode(wav, slot)
        slow_seconds = time.perf_counter() - started

        self.assertEqual(fast, slow)
        # Measured around 24x; assert a conservative floor so this catches a
        # regression to the scalar path without being flaky on a busy machine.
        self.assertLess(fast_seconds * 3, slow_seconds)


if __name__ == "__main__":
    unittest.main()
