"""The seam that lets any audio file reach a slot that accepts only one shape.

This sits in front of the importers and relaxes none of them.  Two properties
carry the whole design and are what these tests hold:

* **A file that is already exact is passed through untouched.**  Not re-encoded,
  not rewritten, not even copied -- the same path comes back.  A modder who
  prepared a precise WAV keeps byte-for-byte control, and the behaviour that
  shipped before this feature existed is unchanged.
* **Anything else is converted and then faces every original check.**  The
  conform output is handed to the same importer as before, so a bug in
  conversion fails closed exactly the way a bad hand-made WAV does.

"Already exact" is deliberately strict about more than the numbers: a WAV
carrying a ``LIST`` tag chunk from a tagging tool has the right shape but the
importers still refuse it, so it must be treated as needing conversion.  That
case is the one most likely to be got wrong, and it has its own test.
"""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import audio_conform  # noqa: E402


def _strict_wav(path: Path, channels: int, rate: int, frames: int,
                amplitude: int = 12000) -> Path:
    samples = []
    for n in range(frames):
        value = amplitude if (n // 24) % 2 == 0 else -amplitude
        for _ in range(channels):
            samples.append(value)
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    path.write_bytes(b"".join((
        b"RIFF", struct.pack("<I", 36 + len(pcm)), b"WAVE", b"fmt ",
        struct.pack("<IHHIIHH", 16, 1, channels, rate,
                    rate * channels * 2, channels * 2, 16),
        b"data", struct.pack("<I", len(pcm)),
    )) + pcm)
    return path


class SuffixTests(unittest.TestCase):
    def test_common_audio_formats_are_offered(self) -> None:
        for suffix in (".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aiff", ".opus"):
            with self.subTest(suffix=suffix):
                self.assertTrue(audio_conform.is_supported_suffix(f"x{suffix}"))

    def test_case_is_ignored(self) -> None:
        self.assertTrue(audio_conform.is_supported_suffix("SOUND.MP3"))
        self.assertTrue(audio_conform.is_supported_suffix("Sound.FlAc"))

    def test_things_that_are_not_audio_are_not_offered(self) -> None:
        for name in ("notes.txt", "art.png", "archive.zip", "movie.iso", "noext"):
            with self.subTest(name=name):
                self.assertFalse(audio_conform.is_supported_suffix(name))

    def test_the_dialog_filter_mentions_the_formats(self) -> None:
        text = audio_conform.file_dialog_filter()
        self.assertIn("*.wav", text)
        self.assertIn("*.mp3", text)
        self.assertIn("*.flac", text)


class ShapeTests(unittest.TestCase):
    def test_a_slots_numbers_become_a_shape(self) -> None:
        shape = audio_conform.shape_for(1, 11025, 10624)
        self.assertEqual(shape.channels, 1)
        self.assertEqual(shape.sample_rate, 11025)
        self.assertEqual(shape.frame_count, 10624)
        self.assertEqual(shape.pcm_bytes, 10624 * 2)

    def test_a_shape_no_slot_could_have_is_refused_by_name(self) -> None:
        """Fails here with a clear message, not four layers down."""

        with self.assertRaises(audio_conform.AudioConformError):
            audio_conform.shape_for(6, 48000, 1024)
        with self.assertRaises(audio_conform.AudioConformError):
            audio_conform.shape_for(1, 11025, 0)


class AlreadyExactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="conform-exact-"))
        self.shape = audio_conform.shape_for(1, 22050, 4096)

    def test_a_matching_strict_wav_is_exact(self) -> None:
        path = _strict_wav(self.root / "good.wav", 1, 22050, 4096)
        self.assertTrue(audio_conform.already_exact(path, self.shape))

    def test_the_wrong_numbers_are_not_exact(self) -> None:
        cases = {
            "rate": _strict_wav(self.root / "rate.wav", 1, 44100, 4096),
            "channels": _strict_wav(self.root / "ch.wav", 2, 22050, 4096),
            "frames": _strict_wav(self.root / "frames.wav", 1, 22050, 2048),
        }
        for label, path in cases.items():
            with self.subTest(wrong=label):
                self.assertFalse(audio_conform.already_exact(path, self.shape))

    def test_a_wav_carrying_a_tag_chunk_is_not_exact(self) -> None:
        """Right shape, but the importers refuse it -- so it needs conversion."""

        pcm = struct.pack(f"<{4096}h", *([9000] * 4096))
        tag = b"LIST" + struct.pack("<I", 10) + b"INFOhello\x00"
        body = b"".join((
            b"fmt ", struct.pack("<IHHIIHH", 16, 1, 1, 22050, 44100, 2, 16),
            tag,
            b"data", struct.pack("<I", len(pcm)), pcm,
        ))
        path = self.root / "tagged.wav"
        path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)
        self.assertFalse(audio_conform.already_exact(path, self.shape))

    def test_a_non_wav_is_never_exact(self) -> None:
        path = self.root / "sound.mp3"
        path.write_bytes(b"\xff\xfb" + bytes(1000))
        self.assertFalse(audio_conform.already_exact(path, self.shape))

    def test_a_missing_file_is_not_exact_rather_than_an_error(self) -> None:
        self.assertFalse(
            audio_conform.already_exact(self.root / "absent.wav", self.shape)
        )


@unittest.skipUnless(
    audio_conform.conversion_available(), "ffmpeg/ffprobe not installed"
)
class ConformTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="conform-"))
        self.workspace = self.root / "work"
        self.workspace.mkdir()

    def test_an_exact_file_is_passed_through_untouched(self) -> None:
        shape = audio_conform.shape_for(1, 22050, 4096)
        source = _strict_wav(self.root / "exact.wav", 1, 22050, 4096)
        before = source.read_bytes()

        result = audio_conform.conform(source, shape, self.workspace)

        self.assertFalse(result.converted)
        self.assertEqual(result.path, source)
        self.assertEqual(source.read_bytes(), before)
        # Nothing was written into the workspace at all.
        self.assertEqual(list(self.workspace.iterdir()), [])
        self.assertIn("unchanged", result.summary)

    def test_a_mismatched_file_is_converted_to_the_exact_shape(self) -> None:
        shape = audio_conform.shape_for(1, 22050, 4096)
        source = _strict_wav(self.root / "wrong.wav", 2, 44100, 44100)

        result = audio_conform.conform(source, shape, self.workspace)

        self.assertTrue(result.converted)
        self.assertNotEqual(result.path, source)
        self.assertEqual(result.path.parent, self.workspace)
        self.assertEqual(result.path.stat().st_size, 44 + shape.pcm_bytes)
        self.assertEqual(result.path.stat().st_nlink, 1)
        # And the conversion output is itself exact, which is the whole point.
        self.assertTrue(audio_conform.already_exact(result.path, shape))
        self.assertTrue(result.notes)

    def test_the_conversion_explains_itself(self) -> None:
        shape = audio_conform.shape_for(1, 22050, 4096)
        source = _strict_wav(self.root / "long.wav", 2, 44100, 44100)
        result = audio_conform.conform(source, shape, self.workspace)
        joined = " ".join(result.notes)
        self.assertIn("Resampled", joined)
        self.assertIn("Channels", joined)

    def test_repeated_conversions_do_not_collide(self) -> None:
        shape = audio_conform.shape_for(1, 22050, 4096)
        source = _strict_wav(self.root / "again.wav", 1, 44100, 44100)
        first = audio_conform.conform(source, shape, self.workspace)
        second = audio_conform.conform(source, shape, self.workspace)
        self.assertNotEqual(first.path, second.path)
        self.assertTrue(first.path.is_file())
        self.assertTrue(second.path.is_file())

    def test_a_file_that_is_not_audio_is_refused(self) -> None:
        shape = audio_conform.shape_for(1, 22050, 4096)
        junk = self.root / "junk.wav"
        junk.write_bytes(b"RIFFnope" * 40)
        with self.assertRaises(audio_conform.AudioConformError):
            audio_conform.conform(junk, shape, self.workspace)

    def test_conversion_output_satisfies_the_real_2k5_parser(self) -> None:
        """The gate this has to clear is the editor's own, not a copy of it."""

        from mod_editor.core import nfl2k5_audo_fixed_slots as fixed

        if not fixed.CAPACITY_REPORT.is_file():
            self.skipTest("retail AUDO capacity evidence is absent: reports/assets/nfl2k5_audo_import_capacity.json")
        slots = fixed.slot_map()
        chosen = sorted(slots.items())[:3]
        source = _strict_wav(self.root / "src.wav", 2, 48000, 48000)
        for key, slot in chosen:
            with self.subTest(slot=key):
                shape = audio_conform.shape_for(
                    slot.channels, slot.sample_rate, slot.frame_count
                )
                workspace = self.root / f"w-{slot.outer_index}-{slot.chunk_index}"
                workspace.mkdir(exist_ok=True)
                result = audio_conform.conform(source, shape, workspace)
                parsed = fixed.parse_strict_wav(result.path.read_bytes(), slot)
                self.assertEqual(parsed.channels, slot.channels)
                self.assertEqual(parsed.sample_rate, slot.sample_rate)
                self.assertEqual(parsed.frame_count, slot.frame_count)


if __name__ == "__main__":
    unittest.main()
