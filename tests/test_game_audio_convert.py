"""Converting a modder's file into a slot's exact shape, without damaging it.

Every audio slot in both games is a fixed channel count, sample rate and frame
count, and the importers reject anything else -- rightly, since a mis-shaped
write is a corrupt slot.  This module is what lets a modder supply an ordinary
file anyway.  The failures it has to prevent are the ones that get misreported
as codec damage:

* a file at the wrong sample rate plays at the wrong speed and pitch;
* a stereo file in a mono slot sounds like noise;
* a channel conversion that quietly changes level by 3 dB;
* a cut made mid-waveform that clicks;
* peaks that clip because band-limited resampling overshoots.

Each of those has a test here.  The pitch test is the important one: it measures
the dominant frequency of the *result*, so a resampler that was configured wrong
is caught by what came out rather than by what was asked for.
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import game_audio_convert as convert  # noqa: E402


def _ffmpeg_present() -> bool:
    return convert.ffmpeg_available()


def _write_wav(path: Path, channel_amplitudes, rate: int, frames: int,
               wave: str = "sine", frequency: float = 440.0) -> Path:
    """A real WAV on disk; the converter reads files, not buffers."""

    samples: list[int] = []
    for n in range(frames):
        if wave == "sine":
            value = math.sin(2 * math.pi * frequency * n / rate)
        else:
            value = 1.0 if (n // 32) % 2 == 0 else -1.0
        for amplitude in channel_amplitudes:
            samples.append(int(max(-1.0, min(1.0, value)) * amplitude))
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    channels = len(channel_amplitudes)
    path.write_bytes(b"".join((
        b"RIFF", struct.pack("<I", 36 + len(pcm)), b"WAVE", b"fmt ",
        struct.pack("<IHHIIHH", 16, 1, channels, rate,
                    rate * channels * 2, channels * 2, 16),
        b"data", struct.pack("<I", len(pcm)),
    )) + pcm)
    return path


def _samples(pcm: bytes):
    return struct.unpack(f"<{len(pcm) // 2}h", pcm)


def _dominant_hz(values, rate: int) -> float:
    """Goertzel-free peak pick over a coarse DFT; enough to catch a speed shift."""

    count = min(len(values), 8192)
    window = values[:count]
    mean = sum(window) / count
    best_frequency = 0.0
    best_power = -1.0
    # 20 Hz resolution over the audible band is plenty to separate 440 Hz from
    # the 220 Hz or 880 Hz a factor-of-two rate error would produce.
    frequency = 40.0
    while frequency < rate / 2:
        real = imaginary = 0.0
        for index, value in enumerate(window):
            angle = 2 * math.pi * frequency * index / rate
            centred = value - mean
            real += centred * math.cos(angle)
            imaginary += centred * math.sin(angle)
        power = real * real + imaginary * imaginary
        if power > best_power:
            best_power = power
            best_frequency = frequency
        frequency += 20.0
    return best_frequency


class ShapeContractTests(unittest.TestCase):
    """No ffmpeg needed."""

    def test_a_shape_knows_its_own_size(self) -> None:
        shape = convert.AudioShape(channels=2, sample_rate=22050, frame_count=1000)
        self.assertEqual(shape.pcm_bytes, 1000 * 2 * 2)
        self.assertAlmostEqual(shape.duration_seconds, 1000 / 22050)
        self.assertIn("stereo", shape.describe())

    def test_shapes_a_game_slot_cannot_have_are_refused(self) -> None:
        for channels, rate, frames in (
            (0, 22050, 100), (3, 22050, 100), (1, 0, 100), (1, 22050, 0),
            (1, 500_000, 100), (1, 22050, -5),
        ):
            with self.subTest(channels=channels, rate=rate, frames=frames):
                with self.assertRaises(convert.AudioConversionError):
                    convert.AudioShape(
                        channels=channels, sample_rate=rate, frame_count=frames
                    )

    def test_channel_arguments_never_rely_on_an_implicit_downmix(self) -> None:
        """-ac normalises differently per sample format; both mixes are explicit."""

        self.assertEqual(convert._channel_arguments(2, 2), ())
        self.assertEqual(
            convert._channel_arguments(1, 2), ("-af", "pan=stereo|c0=c0|c1=c0")
        )
        self.assertEqual(
            convert._channel_arguments(2, 1),
            ("-af", "pan=mono|c0=0.5*c0+0.5*c1"),
        )
        # More than two channels keeps ffmpeg's standard coefficients.
        self.assertEqual(convert._channel_arguments(6, 2), ("-ac", "2"))


class WavWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="convert-wav-"))

    def test_it_writes_the_strict_forty_four_byte_form(self) -> None:
        """Importers reject WAVs carrying tag chunks; this must never emit one."""

        shape = convert.AudioShape(channels=1, sample_rate=11025, frame_count=64)
        pcm = bytes(shape.pcm_bytes)
        written = convert.write_pcm16_wav(pcm, shape, self.root / "out.wav")
        raw = written.read_bytes()

        self.assertEqual(len(raw), 44 + shape.pcm_bytes)
        self.assertEqual(raw[:4], b"RIFF")
        self.assertEqual(raw[8:12], b"WAVE")
        self.assertEqual(raw[12:16], b"fmt ")
        self.assertEqual(raw[36:40], b"data")
        self.assertEqual(struct.unpack_from("<I", raw, 16)[0], 16)
        self.assertEqual(struct.unpack_from("<H", raw, 20)[0], 1)
        self.assertEqual(struct.unpack_from("<I", raw, 40)[0], shape.pcm_bytes)
        self.assertEqual(written.stat().st_nlink, 1)

    def test_it_refuses_a_mismatched_payload_or_suffix(self) -> None:
        shape = convert.AudioShape(channels=1, sample_rate=11025, frame_count=64)
        with self.assertRaises(convert.AudioConversionError):
            convert.write_pcm16_wav(b"short", shape, self.root / "a.wav")
        with self.assertRaises(convert.AudioConversionError):
            convert.write_pcm16_wav(
                bytes(shape.pcm_bytes), shape, self.root / "a.pcm"
            )


@unittest.skipUnless(_ffmpeg_present(), "ffmpeg/ffprobe not installed")
class ConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="convert-"))

    def test_resampling_preserves_pitch(self) -> None:
        """The 'plays at half speed' failure, measured on the output."""

        for rate_in in (8000, 32000, 44100, 48000):
            with self.subTest(source_rate=rate_in):
                source = _write_wav(
                    self.root / f"s{rate_in}.wav", [26000], rate_in, rate_in
                )
                shape = convert.AudioShape(
                    channels=1, sample_rate=22016, frame_count=11008
                )
                pcm, report = convert.convert(source, shape)
                self.assertEqual(len(pcm), shape.pcm_bytes)
                measured = _dominant_hz(_samples(pcm), shape.sample_rate)
                self.assertLess(abs(measured - 440.0), 25.0)
                self.assertEqual(report.resampled, rate_in != shape.sample_rate)

    def test_every_requested_shape_is_produced_exactly(self) -> None:
        source = _write_wav(self.root / "src.wav", [20000, 20000], 44100, 44100)
        for channels in (1, 2):
            for frames in (64, 1024, 30000):
                with self.subTest(channels=channels, frames=frames):
                    shape = convert.AudioShape(
                        channels=channels, sample_rate=22050, frame_count=frames
                    )
                    pcm, _ = convert.convert(source, shape)
                    self.assertEqual(len(pcm), shape.pcm_bytes)

    def test_channel_conversion_does_not_change_level(self) -> None:
        """A silent -3 dB in either direction is the bug this guards."""

        rate = 22050
        shape_mono = convert.AudioShape(
            channels=1, sample_rate=rate, frame_count=rate
        )
        shape_stereo = convert.AudioShape(
            channels=2, sample_rate=rate, frame_count=rate
        )

        mono = _write_wav(self.root / "m.wav", [20000], rate, rate, wave="square")
        pcm, _ = convert.convert(mono, shape_stereo, limit_peak=False)
        values = _samples(pcm)
        for channel in (0, 1):
            peak = max(abs(v) for v in values[channel::2])
            self.assertAlmostEqual(peak / 20000, 1.0, delta=0.03)

        both = _write_wav(
            self.root / "b.wav", [20000, 20000], rate, rate, wave="square"
        )
        pcm, _ = convert.convert(both, shape_mono, limit_peak=False)
        peak = max(abs(v) for v in _samples(pcm))
        self.assertAlmostEqual(peak / 20000, 1.0, delta=0.03)

        # A true average, not an energy-preserving rule: one silent channel
        # halves the result.
        left = _write_wav(self.root / "l.wav", [20000, 0], rate, rate, wave="square")
        pcm, _ = convert.convert(left, shape_mono, limit_peak=False)
        peak = max(abs(v) for v in _samples(pcm))
        self.assertAlmostEqual(peak / 20000, 0.5, delta=0.03)

    def test_padding_and_trimming_are_reported(self) -> None:
        rate = 22050
        shape = convert.AudioShape(channels=1, sample_rate=rate, frame_count=rate)

        short = _write_wav(self.root / "short.wav", [18000], rate, rate // 5)
        _, report = convert.convert(short, shape)
        self.assertGreater(report.frames_padded, 0)
        self.assertEqual(report.frames_trimmed, 0)
        self.assertTrue(any("padded" in note for note in report.notes))

        long_source = _write_wav(self.root / "long.wav", [18000], rate, rate * 3)
        _, report = convert.convert(long_source, shape)
        self.assertGreater(report.frames_trimmed, 0)
        self.assertEqual(report.frames_padded, 0)
        self.assertTrue(report.faded_at_trim)
        self.assertTrue(any("trimmed" in note for note in report.notes))

    def test_the_trim_fade_lands_the_cut_near_zero(self) -> None:
        """A hard cut mid-waveform is heard as a click."""

        rate = 22050
        shape = convert.AudioShape(channels=1, sample_rate=rate, frame_count=rate)
        source = _write_wav(self.root / "cut.wav", [26000], rate, rate * 3)

        faded, _ = convert.convert(source, shape, fade_on_trim=True)
        abrupt, _ = convert.convert(source, shape, fade_on_trim=False)
        self.assertLess(abs(_samples(faded)[-1]), abs(_samples(abrupt)[-1]))
        self.assertLess(abs(_samples(faded)[-1]), 64)

    def test_an_exact_source_is_reported_as_untouched(self) -> None:
        rate = 22050
        shape = convert.AudioShape(channels=1, sample_rate=rate, frame_count=rate)
        source = _write_wav(self.root / "exact.wav", [15000], rate, rate)
        _, report = convert.convert(source, shape)
        self.assertFalse(report.resampled)
        self.assertFalse(report.channels_changed)
        self.assertEqual(report.frames_padded, 0)
        self.assertEqual(report.frames_trimmed, 0)
        self.assertIn("nothing was altered", " ".join(report.notes))

    def test_peaks_are_kept_below_full_scale(self) -> None:
        rate = 22050
        shape = convert.AudioShape(channels=1, sample_rate=rate, frame_count=rate)
        loud = _write_wav(self.root / "loud.wav", [32767], rate, rate, wave="square")
        pcm, report = convert.convert(loud, shape, limit_peak=True)
        self.assertLessEqual(report.peak_after, convert.PEAK_CEILING + 1e-6)
        self.assertLess(max(abs(v) for v in _samples(pcm)), 32767)

    def test_compressed_sources_are_accepted(self) -> None:
        rate = 22050
        shape = convert.AudioShape(channels=1, sample_rate=rate, frame_count=rate)
        source = _write_wav(self.root / "seed.wav", [22000, 22000], 44100, 44100)
        for codec, suffix in (("libmp3lame", ".mp3"), ("flac", ".flac"),
                              ("libvorbis", ".ogg")):
            encoded = self.root / f"encoded{suffix}"
            completed = subprocess.run(
                ["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
                 "-acodec", codec, "-y", str(encoded)],
                capture_output=True,
            )
            if completed.returncode != 0:
                self.skipTest(f"{codec} unavailable in this ffmpeg build")
            with self.subTest(codec=codec):
                pcm, report = convert.convert(encoded, shape)
                self.assertEqual(len(pcm), shape.pcm_bytes)
                measured = _dominant_hz(_samples(pcm), rate)
                self.assertLess(abs(measured - 440.0), 30.0)

    def test_files_that_are_not_audio_are_refused(self) -> None:
        shape = convert.AudioShape(channels=1, sample_rate=22050, frame_count=1024)

        junk = self.root / "junk.bin"
        junk.write_bytes(b"not audio" * 200)
        with self.assertRaises(convert.AudioConversionError):
            convert.convert(junk, shape)

        with self.assertRaises(FileNotFoundError):
            convert.probe(self.root / "missing.wav")

        empty = self.root / "empty.wav"
        empty.write_bytes(b"")
        with self.assertRaises(convert.AudioConversionError):
            convert.convert(empty, shape)

    def test_a_symlink_is_refused(self) -> None:
        shape = convert.AudioShape(channels=1, sample_rate=22050, frame_count=1024)
        real = _write_wav(self.root / "real.wav", [10000], 22050, 22050)
        link = self.root / "link.wav"
        link.symlink_to(real)
        with self.assertRaises(convert.AudioConversionError):
            convert.convert(link, shape)


if __name__ == "__main__":
    unittest.main()
