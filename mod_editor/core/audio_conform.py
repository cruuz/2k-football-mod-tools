"""Let a modder drop any audio file into a slot that only accepts one shape.

Every audio importer in both editors demands an exact match: the slot's channel
count, its sample rate, and its exact frame count, in a strict RIFF PCM16 WAV
carrying nothing but ``fmt `` and ``data``.  Those importers are right to demand
it -- a mis-shaped write is a corrupt slot -- but it leaves the modder doing the
shaping by hand in an audio editor, and that is where almost every "the audio
came out weird" report actually begins.  A file at the wrong sample rate plays
at the wrong speed and pitch; a stereo file in a mono slot sounds like noise;
a hand-trimmed file clicks at the cut.

This module sits *in front of* those importers and changes none of them.  It
converts what the modder supplied into exactly what the slot wants, writes it as
the strict WAV the existing parser already accepts, and hands that file on.  The
conformed file then passes through every validation that was there before,
unmodified -- so a bug here fails closed, exactly like a bad hand-made WAV.

Two things it deliberately does not do.  It never converts a file that is
already exactly right: that file is passed through untouched, so a modder who
prepared a precise WAV keeps byte-for-byte control and nothing is silently
re-encoded underneath them.  And it never invents an encoder -- FFmpeg is used
only to decode and resample the modder's own file into PCM, and the game's own
codec step stays where it always was.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


def _convert_module():
    """The shared converter, imported the way the rest of core imports tools/."""

    tools = str(Path(__file__).resolve().parents[2] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    try:
        import game_audio_convert as module
    except ImportError:  # pragma: no cover - lean checkouts without tools/
        return None
    return module


#: Extensions offered in the file chooser and accepted by the drop zones.
#: FFmpeg reads far more than this, and anything it can decode will work; the
#: list exists so a drag of an unrelated file is refused by the widget rather
#: than after a failed decode.  ``.wav`` stays first because an exact WAV is
#: still the passthrough case.
SUPPORTED_SUFFIXES: tuple[str, ...] = (
    ".wav", ".mp3", ".flac", ".ogg", ".oga", ".opus", ".m4a", ".aac",
    ".wma", ".aiff", ".aif", ".aifc", ".caf", ".w64", ".mp4", ".mkv",
    ".webm", ".mov", ".avi", ".ac3", ".au", ".snd", ".voc", ".ape",
    ".wv", ".tta", ".mpc", ".spx", ".amr", ".3gp", ".m4b", ".mka",
)


def file_dialog_filter() -> str:
    """A Qt chooser filter covering everything the converter accepts."""

    patterns = " ".join(f"*{suffix}" for suffix in SUPPORTED_SUFFIXES)
    return (
        f"Audio files ({patterns});;"
        "Exact PCM16 WAV (*.wav);;"
        "All files (*)"
    )


def is_supported_suffix(path) -> bool:
    return Path(path).suffix.casefold() in SUPPORTED_SUFFIXES


class AudioConformError(ValueError):
    """The supplied audio could not be made to fit the slot."""


@dataclass(frozen=True)
class ConformResult:
    """Which file to import, and what had to happen to get it."""

    path: Path
    converted: bool
    notes: tuple[str, ...]
    #: ``None`` when the supplied file was already exact and was passed through.
    report: object | None = None

    @property
    def summary(self) -> str:
        """One line for a status bar; the notes are the single source of truth."""

        return " ".join(self.notes)


def conversion_available() -> bool:
    """Whether conversion can run, so a GUI can say so before offering it."""

    module = _convert_module()
    return module is not None and module.ffmpeg_available()


def shape_for(channels: int, sample_rate: int, frame_count: int):
    """Build the converter's target shape from a slot's own numbers."""

    module = _convert_module()
    if module is None:  # pragma: no cover - lean checkouts without tools/
        raise AudioConformError("The audio converter is unavailable")
    try:
        return module.AudioShape(
            channels=channels, sample_rate=sample_rate, frame_count=frame_count
        )
    except ValueError as exc:
        raise AudioConformError(str(exc)) from exc


def already_exact(path, shape) -> bool:
    """Is this already the strict WAV the slot wants, byte for byte?

    Checked by parsing rather than by trusting the extension, and deliberately
    strict in the same way the importers are: a WAV carrying an extra ``LIST``
    chunk from a tagging tool is *not* exact, because the importer will refuse
    it, so it must go through conversion to be normalised.
    """

    import struct

    candidate = Path(path)
    if candidate.suffix.casefold() != ".wav":
        return False
    try:
        if not candidate.is_file():
            return False
        expected = 44 + shape.pcm_bytes
        if candidate.stat().st_size != expected:
            return False
        with open(candidate, "rb") as handle:
            header = handle.read(44)
    except OSError:
        return False

    if len(header) != 44:
        return False
    if header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
        return False
    if header[12:16] != b"fmt " or header[36:40] != b"data":
        return False

    riff_size = struct.unpack_from("<I", header, 4)[0]
    fmt_size = struct.unpack_from("<I", header, 16)[0]
    tag, channels, rate, byte_rate, block_align, bits = struct.unpack_from(
        "<HHIIHH", header, 20
    )
    data_size = struct.unpack_from("<I", header, 40)[0]

    return (
        riff_size == 36 + shape.pcm_bytes
        and fmt_size == 16
        and tag == 1
        and bits == 16
        and channels == shape.channels
        and rate == shape.sample_rate
        and block_align == shape.channels * 2
        and byte_rate == shape.sample_rate * shape.channels * 2
        and data_size == shape.pcm_bytes
    )


def conform(supplied, shape, destination_directory) -> ConformResult:
    """Return a file matching ``shape``, converting only if it has to.

    ``destination_directory`` must already exist and be private to the caller;
    the converted WAV is created inside it with an exclusive create, so it is a
    fresh regular file with one link -- which is what the stricter importers
    require of anything they are handed.
    """

    module = _convert_module()
    if module is None:  # pragma: no cover - lean checkouts without tools/
        raise AudioConformError("The audio converter is unavailable")

    source = Path(supplied)
    if already_exact(source, shape):
        return ConformResult(path=source, converted=False, notes=(
            "This file already matches the slot exactly, so it was used "
            "unchanged.",
        ))

    if not module.ffmpeg_available():
        raise AudioConformError(
            "This file is not already an exact match for the slot, and FFmpeg "
            "was not found to convert it. Install FFmpeg, or supply a WAV that "
            f"is exactly {shape.describe()}."
        )

    try:
        pcm, report = module.convert(source, shape)
    except ValueError as exc:
        raise AudioConformError(str(exc)) from exc

    directory = Path(destination_directory)
    destination = directory / "conformed.wav"
    counter = 0
    while destination.exists():
        counter += 1
        destination = directory / f"conformed-{counter}.wav"
        if counter > 4096:
            raise AudioConformError("Could not create a conversion workspace")

    try:
        module.write_pcm16_wav(pcm, shape, destination)
    except (OSError, ValueError) as exc:
        raise AudioConformError(f"Could not write the converted audio: {exc}") from exc

    return ConformResult(
        path=destination,
        converted=True,
        notes=tuple(report.notes),
        report=report,
    )


@dataclass(frozen=True)
class MusicConformReport:
    """Fixed music fit v1. RMS uses useful content, never its padding tail."""

    source_seconds: float
    slot_seconds: float
    trimmed_seconds: float
    padded_seconds: float
    fade_seconds: float
    original_rms: float
    input_rms: float
    output_rms: float
    gain_db: float
    peak_limited: bool
    gain_capped: bool
    match_volume: bool
    notes: tuple[str, ...]

    @property
    def summary(self):
        return (f"File {self.source_seconds:.3f} s; slot {self.slot_seconds:.3f} s; "
                f"trimmed {self.trimmed_seconds:.3f} s; "
                f"silence added {self.padded_seconds:.3f} s. " + " ".join(self.notes))


def _pcm_samples(pcm):
    import array
    import sys
    samples = array.array("h", pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _pcm_bytes(samples):
    import sys
    if sys.byteorder != "little":
        samples = samples[:]
        samples.byteswap()
    return samples.tobytes()


def music_rms(pcm):
    import math
    samples = _pcm_samples(pcm)
    return math.sqrt(sum(x*x for x in samples) / len(samples)) / 32768 if samples else 0.0


def music_downmix(pcm):
    """Arithmetic (L+R)/2 after stereo gain; report destructive cancellation."""
    import array
    values = _pcm_samples(pcm)
    if len(values) % 2:
        raise AudioConformError("Stereo audio has an incomplete frame")
    mono = _pcm_bytes(array.array("h", (round((values[i]+values[i+1])/2)
                                       for i in range(0, len(values), 2))))
    cancellation = music_rms(pcm) > 1/32768 and music_rms(mono) < music_rms(pcm)*0.1
    return mono, cancellation


def conform_music(supplied, shape, original_pcm: bytes, *, match_volume=True,
                  cancelled=None):
    """Return exact PCM and a report without changing the other panels' defaults.

    Gain is capped at +12 dB and peaks at -1 dBFS. Silent input/original uses
    unity gain (peak protection still applies). Fade the last 50 ms on trim.
    Native 22050-Hz PCM16 WAV fits without FFmpeg, including mono/stereo remix.
    Other formats/rates use the existing bounded FFmpeg/FFprobe converter.
    Cancellation is checked around conversion and during the PCM processing.
    """
    import array
    import math
    import wave
    from .json_stream import read_bounded_regular_file
    import io

    def check():
        if cancelled and cancelled():
            raise AudioConformError("Music import cancelled; nothing was changed")

    check()
    if type(match_volume) is not bool or shape.sample_rate != 22050:
        raise AudioConformError("Music requires 22050 Hz and a boolean volume switch")
    if len(original_pcm) != shape.pcm_bytes:
        raise AudioConformError("Original music does not match the target slot")
    source = Path(supplied)
    module = _convert_module()
    if module is None:
        raise AudioConformError("The audio converter is unavailable")
    native = None
    downmix_cancelled = False
    if source.suffix.lower() == ".wav":
        _path, payload = read_bounded_regular_file(source, "Music WAV", maximum=module.MAX_SOURCE_BYTES)
        try:
            with wave.open(io.BytesIO(payload), "rb") as wav:
                if wav.getsampwidth() == 2 and wav.getframerate() == 22050 and wav.getnchannels() in (1, 2):
                    frames, channels = wav.getnframes(), wav.getnchannels()
                    if not 0 < frames*channels*2 <= module.MAX_DECODED_BYTES:
                        raise AudioConformError("Music WAV exceeds the decode limit or is empty")
                    pcm = wav.readframes(frames)
                    if len(pcm) != frames*channels*2:
                        raise AudioConformError("Music WAV is truncated")
                    if channels == 2 and shape.channels == 1:
                        pcm, downmix_cancelled = music_downmix(pcm)
                    elif channels == 1 and shape.channels == 2:
                        pcm = _pcm_bytes(array.array("h", (v for x in _pcm_samples(pcm) for v in (x,x))))
                    native = (pcm, frames)
        except (wave.Error, EOFError):
            pass
    converter_limited = False
    if native is None:
        if not module.ffmpeg_available():
            raise AudioConformError("Install FFmpeg and FFprobe to import this file, or supply a "
                                    "22050 Hz PCM16 mono/stereo WAV. Music keeps the slot length.")
        pcm, report = module.convert(source, shape, fade_on_trim=False, cancelled=cancelled)
        seconds = report.source.duration_seconds
        supplied_frames = max(1, round(seconds*shape.sample_rate))
        useful = min(shape.frame_count, report.frames_supplied)
        converter_limited = report.limited
    else:
        pcm, supplied_frames = native
        seconds = supplied_frames/shape.sample_rate
        useful = min(shape.frame_count, supplied_frames)
    check()
    samples = _pcm_samples(pcm[:useful*shape.channels*2])
    input_rms = music_rms(_pcm_bytes(samples))
    baseline = music_rms(original_pcm)
    notes = []
    if downmix_cancelled:
        notes.append("The mono version is nearly silent because the stereo channels cancel.")
    wanted = 1.0
    if match_volume and baseline > 1/32768 and input_rms > 1/32768:
        wanted = baseline/input_rms
    elif match_volume:
        notes.append("Silent input or original: volume gain left unchanged.")
    gain = min(wanted, 10**(12/20))
    gain_capped = gain < wanted
    peak = max((abs(x)/32768 for x in samples), default=0)
    ceiling = 10**(-1/20)
    limited = peak*gain > ceiling
    if limited:
        gain = ceiling/peak
    if gain_capped:
        notes.append("Volume gain capped at +12 dB; original RMS may not be reached.")
    if limited or converter_limited:
        notes.append("Peak protection reduced volume; original RMS may not be reached.")
    trimmed = max(0, supplied_frames-shape.frame_count)
    fade = min(useful, round(0.05*shape.sample_rate)) if trimmed else 0
    for i, sample in enumerate(samples):
        if i % 32768 == 0:
            check()
        frame = i//shape.channels
        scale = gain
        if fade and frame >= useful-fade:
            scale *= (useful-1-frame)/max(1, fade-1)
        samples[i] = max(-32768, min(32767, round(sample*scale)))
    output_rms = music_rms(_pcm_bytes(samples))
    samples.extend(array.array("h", bytes((shape.frame_count-useful)*shape.channels*2)))
    check()
    return _pcm_bytes(samples), MusicConformReport(
        seconds, shape.duration_seconds, trimmed/shape.sample_rate,
        max(0, shape.frame_count-useful)/shape.sample_rate, fade/shape.sample_rate,
        baseline, input_rms, output_rms, 20*math.log10(gain),
        limited or converter_limited, gain_capped, match_volume, tuple(notes))
