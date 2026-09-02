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
