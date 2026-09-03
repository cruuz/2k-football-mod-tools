#!/usr/bin/env python3
"""Turn any audio file a modder has into the exact shape a game slot demands.

Both editors replace audio into *fixed* slots: a slot is a specific channel
count, a specific sample rate, and a specific number of PCM frames, and the
game will not negotiate.  Every importer downstream of this module therefore
rejects anything that is not shaped exactly right -- correctly, because a
mis-shaped write is a corrupt slot.

That leaves the modder doing the shaping by hand, which is where "the audio
came out weird" almost always begins.  The complaints blamed on codecs are
usually not codec damage at all:

* **wrong sample rate** -- by far the most common.  Dropping 44.1 kHz audio into
  a 22.05 kHz slot without resampling plays it at half speed an octave down.
  Nothing about that is subtle, but it gets described as "the encoder ruined it".
* **wrong channel count** -- a stereo file written into a mono slot interleaves
  L and R into one stream, which sounds like ring-modulated noise.
* **naive normalisation** -- peak-normalising to full scale, then encoding with a
  lossy codec whose reconstruction overshoots slightly, clips on playback.
* **hard truncation** -- cutting a sound mid-waveform to make it fit puts a step
  discontinuity at the end, heard as a click.

This module removes all four by doing the conversion properly and *reporting*
what it did, so a surprising result is visible rather than mysterious.  FFmpeg
does the decoding and resampling (with the soxr resampler at high precision, not
the default linear one), and the result is checked to be exactly the requested
shape before it is handed on.

FFmpeg is invoked as an argv vector, never through a shell, and only ever
writes into a private temporary directory.  It is used solely to *decode* the
modder's own file; no game audio passes through it.
"""

from __future__ import annotations

import array
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

BYTES_PER_SAMPLE = 2

#: The decode stays in float32 so resampler overshoot can be measured before it
#: is quantised; that intermediate is twice the size of the PCM16 result.
FLOAT_BYTES_PER_SAMPLE = 4

MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_DECODED_BYTES = 512 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 300.0

#: Trimming mid-waveform leaves a step discontinuity that is heard as a click.
#: A short fade into the cut removes it and is inaudible as a fade at this
#: length.  Kept small so it cannot audibly shorten a sound effect.
TRIM_FADE_FRAMES = 256

#: Headroom applied when peak-limiting is requested.  Lossy reconstruction can
#: overshoot the original peak slightly, so landing exactly at full scale is how
#: clipping gets introduced on playback rather than avoided.
PEAK_CEILING = 0.985


class AudioConversionError(ValueError):
    """The supplied audio cannot be converted into the requested shape."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AudioConversionError(message)


@dataclass(frozen=True)
class AudioShape:
    """Exactly what one game slot accepts."""

    channels: int
    sample_rate: int
    frame_count: int

    def __post_init__(self) -> None:
        _require(
            type(self.channels) is int and self.channels in (1, 2),
            "A game audio slot must be mono or stereo",
        )
        _require(
            type(self.sample_rate) is int and 1 <= self.sample_rate <= 384_000,
            "Slot sample rate is outside the supported range",
        )
        _require(
            type(self.frame_count) is int and 0 < self.frame_count <= 400_000_000,
            "Slot frame count is outside the supported range",
        )
        _require(
            self.pcm_bytes <= MAX_DECODED_BYTES,
            "Slot shape is larger than the decode ceiling",
        )

    @property
    def pcm_bytes(self) -> int:
        return self.frame_count * self.channels * BYTES_PER_SAMPLE

    @property
    def duration_seconds(self) -> float:
        return self.frame_count / self.sample_rate

    def describe(self) -> str:
        layout = "mono" if self.channels == 1 else "stereo"
        return (f"{layout} {self.sample_rate} Hz, {self.frame_count} frames "
                f"({self.duration_seconds:.2f} s)")


@dataclass(frozen=True)
class SourceAudio:
    """What the modder actually supplied, as probed."""

    path: Path
    size: int
    codec: str
    channels: int
    sample_rate: int
    duration_seconds: float

    def describe(self) -> str:
        layout = {1: "mono", 2: "stereo"}.get(self.channels, f"{self.channels}ch")
        return (f"{self.codec} {layout} {self.sample_rate} Hz, "
                f"{self.duration_seconds:.2f} s")


@dataclass(frozen=True)
class ConversionReport:
    """Everything that happened, so a surprising result is explainable."""

    source: SourceAudio
    shape: AudioShape
    resampled: bool
    channels_changed: bool
    frames_supplied: int
    frames_padded: int
    frames_trimmed: int
    faded_at_trim: bool
    peak_before: float
    peak_after: float
    limited: bool

    @property
    def notes(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.resampled:
            out.append(
                f"Resampled {self.source.sample_rate} Hz -> {self.shape.sample_rate} Hz "
                "(soxr). Without this the sound would play at the wrong speed and pitch."
            )
        if self.channels_changed:
            out.append(
                f"Channels {self.source.channels} -> {self.shape.channels}."
            )
        if self.frames_trimmed:
            trimmed = self.frames_trimmed / self.shape.sample_rate
            note = (f"Source was longer than the slot; trimmed {self.frames_trimmed} "
                    f"frames ({trimmed:.2f} s).")
            if self.faded_at_trim:
                note += " A short fade was applied at the cut so it does not click."
            out.append(note)
        if self.frames_padded:
            padded = self.frames_padded / self.shape.sample_rate
            out.append(
                f"Source was shorter than the slot; padded {self.frames_padded} "
                f"frames ({padded:.2f} s) of silence. The slot is a fixed size."
            )
        if self.limited:
            out.append(
                f"Peak {self.peak_before:.3f} reduced to {self.peak_after:.3f} "
                "to leave headroom, because lossy reconstruction overshoots and "
                "would clip at full scale."
            )
        if not out:
            out.append("Source already matched the slot exactly; nothing was altered.")
        return tuple(out)


def _tool(name: str) -> str:
    found = shutil.which(name)
    _require(
        found is not None,
        f"{name} was not found. Install FFmpeg to convert audio; it is used only "
        f"to decode your own file.",
    )
    return found


def ffmpeg_available() -> bool:
    """Whether conversion can run at all, for a GUI to check before offering it."""

    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _open_source(path) -> Path:
    _require(isinstance(path, (str, Path)), "Audio source must be a path")
    resolved = Path(path)
    supplied = resolved.lstat()
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        "Audio source must be a regular file, not a symlink or device",
    )
    _require(supplied.st_size > 0, "Audio source is empty")
    _require(
        supplied.st_size <= MAX_SOURCE_BYTES,
        f"Audio source is larger than {MAX_SOURCE_BYTES // (1024 * 1024)} MiB",
    )
    return resolved.resolve(strict=True)


def probe(path, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> SourceAudio:
    """Read the source's real shape rather than trusting its extension."""

    resolved = _open_source(path)
    command = (
        _tool("ffprobe"),
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,channels,sample_rate:format=duration",
        "-of", "json",
        str(resolved),
    )
    try:
        completed = subprocess.run(
            command, capture_output=True, timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioConversionError("ffprobe timed out reading the audio source") from exc
    _require(
        completed.returncode == 0,
        "ffprobe could not read that file as audio: "
        + (completed.stderr.decode("utf-8", "replace").strip().splitlines() or [""])[-1],
    )
    try:
        parsed = json.loads(completed.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as exc:
        raise AudioConversionError("ffprobe returned unreadable output") from exc

    streams = parsed.get("streams") or []
    _require(bool(streams), "That file contains no audio stream")
    stream = streams[0]

    try:
        channels = int(stream["channels"])
        sample_rate = int(stream["sample_rate"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AudioConversionError("Audio stream is missing its shape") from exc

    duration = 0.0
    raw_duration = (parsed.get("format") or {}).get("duration")
    if raw_duration is not None:
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            duration = 0.0

    _require(channels >= 1, "Audio stream reports no channels")
    _require(sample_rate >= 1, "Audio stream reports no sample rate")

    return SourceAudio(
        path=resolved,
        size=resolved.stat().st_size,
        codec=str(stream.get("codec_name") or "unknown"),
        channels=channels,
        sample_rate=sample_rate,
        duration_seconds=duration,
    )


def _channel_arguments(source_channels: int, target_channels: int) -> tuple[str, ...]:
    """Change channel count without letting a default quietly change the level.

    ``-ac`` is deliberately avoided for the mono/stereo cases.  Measured on
    ffmpeg 6.1.1, its implicit downmix does not even normalise consistently
    across output formats: decoding stereo to mono lands at ``(L+R)/2`` when the
    output is ``s16le`` but at ``(L+R)/sqrt(2)`` when it is ``f32le`` -- a
    3 dB difference caused by nothing but the sample format chosen downstream.
    Mono to stereo attenuates each output channel to 1/sqrt(2) as well.

    None of that is worth tracking through FFmpeg version changes, so the two
    mixes that matter are written out explicitly and mean exactly what they say.
    Sources with more than two channels keep ``-ac``, whose multichannel
    coefficients are standard and better than anything hand-rolled here; any
    resulting overshoot is caught by the float headroom check rather than by
    hoping FFmpeg normalised it.
    """

    if source_channels == target_channels:
        return ()
    if source_channels == 1 and target_channels == 2:
        return ("-af", "pan=stereo|c0=c0|c1=c0")
    if source_channels == 2 and target_channels == 1:
        return ("-af", "pan=mono|c0=0.5*c0+0.5*c1")
    return ("-ac", str(target_channels))


def _decode(source: SourceAudio, shape: AudioShape, timeout: float) -> bytes:
    """Decode to headerless float32 at the target rate and channel count.

    Float rather than PCM16 on purpose.  Band-limited resampling overshoots on
    transients -- a square-ish waveform taken from 48 kHz to 11 kHz measures
    ~1.18x its source peak, which is Gibbs ringing and entirely correct
    behaviour.  Decoding straight to ``s16le`` would let FFmpeg clip that
    overshoot before this module ever saw it, so the headroom check further
    down would be inspecting audio that had already been damaged.  Staying in
    float until the very end means the peak is measured honestly, any reduction
    happens before quantisation, and the signal is quantised exactly once.
    """

    channel_arguments = _channel_arguments(source.channels, shape.channels)
    # The default resampler is fast and audibly poor on the large rate ratios
    # game slots need (48000 -> 22050 and similar). soxr at high precision is
    # the reason a converted file sounds like the original rather than like a
    # cheap sample-rate conversion.
    resample = f"aresample={shape.sample_rate}:resampler=soxr:precision=28"

    # A single -af wins over an earlier one, so a pan and a resample have to be
    # chained into one filter string rather than passed as two flags.
    if channel_arguments[:1] == ("-af",):
        filters = ("-af", f"{channel_arguments[1]},{resample}")
    else:
        filters = channel_arguments + ("-af", resample)

    # A slot holds a fixed number of frames, so decoding beyond that is work
    # thrown away -- and for a long source it is a lot of work: an hour of
    # stereo at 48 kHz is 1.4 GiB of float, which would trip the size ceiling
    # and refuse a file that is perfectly usable. Decoding only what the slot
    # can hold turns that refusal into a success. The margin covers resampler
    # edge effects and rounding so the fit logic below still sees a full slot.
    limit = shape.frame_count / shape.sample_rate + 0.5

    with tempfile.TemporaryDirectory(prefix="game-audio-convert-") as directory:
        destination = Path(directory) / "decoded.pcm"
        command = (
            _tool("ffmpeg"),
            "-nostdin",
            "-v", "error",
            "-i", str(source.path),
            "-map", "a:0",
            "-t", f"{limit:.6f}",
            *filters,
            "-f", "f32le",
            "-acodec", "pcm_f32le",
            "-y",
            str(destination),
        )
        try:
            completed = subprocess.run(
                command, capture_output=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioConversionError("ffmpeg timed out decoding the audio") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            last = detail.splitlines()[-1] if detail else "no diagnostic output"
            raise AudioConversionError(f"ffmpeg could not decode that audio: {last}")

        _require(destination.is_file(), "ffmpeg produced no output")
        produced = destination.stat().st_size
        _require(produced > 0, "ffmpeg produced an empty decode")
        _require(
            produced <= MAX_DECODED_BYTES,
            "Decoded audio exceeds the size ceiling",
        )
        with open(destination, "rb") as handle:
            data = handle.read()
    _require(len(data) == produced, "Decoded audio changed size while reading")
    return data


def _peak(samples) -> float:
    """Peak as a fraction of full scale, in float terms."""

    if not len(samples):
        return 0.0
    return max(max(samples), -min(samples))


def _quantize(samples) -> bytes:
    """Float to PCM16, rounding half away from zero and clamping the rails.

    Truncation would bias every sample toward zero and add avoidable noise, so
    the rounding is explicit.  Clamping happens here and only here, because by
    this point the peak has already been brought inside full scale if it needed
    to be -- anything still on the rail is genuinely a full-scale sample rather
    than an overshoot that should have been caught earlier.
    """

    out = array.array("h", bytes(2 * len(samples)))
    for position, value in enumerate(samples):
        scaled = value * 32767.0
        rounded = int(scaled + 0.5) if scaled >= 0.0 else int(scaled - 0.5)
        if rounded > 32_767:
            rounded = 32_767
        elif rounded < -32_768:
            rounded = -32_768
        out[position] = rounded
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()


def convert(
    path,
    shape: AudioShape,
    *,
    limit_peak: bool = True,
    fade_on_trim: bool = True,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bytes, ConversionReport]:
    """Convert any audio file into exactly ``shape``, and say what was done.

    Returns interleaved little-endian PCM16 of exactly ``shape.pcm_bytes``
    bytes, which is what every importer here consumes.
    """

    _require(isinstance(shape, AudioShape), "A target AudioShape is required")
    source = probe(path, timeout=timeout)
    decoded = _decode(source, shape, timeout)

    frame_bytes = shape.channels * FLOAT_BYTES_PER_SAMPLE
    _require(
        len(decoded) % frame_bytes == 0,
        "Decoded audio does not contain whole frames",
    )
    supplied_frames = len(decoded) // frame_bytes
    _require(supplied_frames > 0, "Decoded audio contains no frames")

    samples = array.array("f")
    samples.frombytes(decoded)
    if sys.byteorder != "little":
        samples.byteswap()
    peak_before = _peak(samples)

    trimmed = 0
    padded = 0
    faded = False

    if supplied_frames > shape.frame_count:
        trimmed = supplied_frames - shape.frame_count
        # The decode stopped at roughly one slot's worth, so the buffer cannot
        # say how much was really left behind. The source's own duration can,
        # and that is the number worth telling someone who dropped a whole song
        # onto a one-second slot.
        if source.duration_seconds > 0.0:
            from_source = (
                int(round(source.duration_seconds * shape.sample_rate))
                - shape.frame_count
            )
            trimmed = max(trimmed, from_source)
        del samples[shape.frame_count * shape.channels:]
        if fade_on_trim and shape.frame_count > TRIM_FADE_FRAMES:
            faded = True
            fade = min(TRIM_FADE_FRAMES, shape.frame_count)
            start = shape.frame_count - fade
            for offset in range(fade):
                gain = (fade - 1 - offset) / fade
                base = (start + offset) * shape.channels
                for channel in range(shape.channels):
                    samples[base + channel] *= gain
    elif supplied_frames < shape.frame_count:
        padded = shape.frame_count - supplied_frames
        samples.extend(array.array("f", bytes(
            FLOAT_BYTES_PER_SAMPLE * padded * shape.channels
        )))

    limited = False
    peak_after = _peak(samples)
    if limit_peak and peak_after > PEAK_CEILING:
        limited = True
        scale = PEAK_CEILING / peak_after
        for position in range(len(samples)):
            samples[position] *= scale
        peak_after = _peak(samples)

    pcm = _quantize(samples)
    _require(
        len(pcm) == shape.pcm_bytes,
        f"Converted audio is {len(pcm)} bytes but the slot needs {shape.pcm_bytes}",
    )

    report = ConversionReport(
        source=source,
        shape=shape,
        resampled=source.sample_rate != shape.sample_rate,
        channels_changed=source.channels != shape.channels,
        frames_supplied=supplied_frames,
        frames_padded=padded,
        frames_trimmed=trimmed,
        faded_at_trim=faded,
        peak_before=peak_before,
        peak_after=peak_after,
        limited=limited,
    )
    return pcm, report


def write_pcm16_wav(pcm: bytes, shape: AudioShape, destination) -> Path:
    """Wrap converted PCM in the strict 44-byte fmt+data WAV importers expect.

    Deliberately emits only ``fmt `` then ``data`` with no metadata chunks: the
    strict parsers here reject anything else, and a WAV carrying a ``LIST`` tag
    from a tagging tool is a common reason a hand-made file is refused.
    """

    _require(
        len(pcm) == shape.pcm_bytes,
        "PCM length does not match the shape being written",
    )
    target = Path(destination)
    _require(target.suffix.lower() == ".wav", "PCM template must end in .wav")

    byte_rate = shape.sample_rate * shape.channels * BYTES_PER_SAMPLE
    block_align_bytes = shape.channels * BYTES_PER_SAMPLE
    header = b"".join((
        b"RIFF",
        struct.pack("<I", 36 + len(pcm)),
        b"WAVE",
        b"fmt ",
        struct.pack(
            "<IHHIIHH",
            16, 1, shape.channels, shape.sample_rate,
            byte_rate, block_align_bytes, 16,
        ),
        b"data",
        struct.pack("<I", len(pcm)),
    ))
    _require(len(header) == 44, "internal WAV header size differs")

    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
        0o644,
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(header)
            handle.write(pcm)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    """Convert one file from the command line.

    The editors call ``convert`` directly; this exists so the same conversion
    can be run and inspected outside a GUI -- to prepare a batch of files, or to
    see exactly what a slot's shape does to a particular source.
    """

    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Convert any audio file into the exact PCM16 WAV a game audio slot "
            "accepts."
        ),
    )
    parser.add_argument("source", type=Path, help="audio file to convert")
    parser.add_argument("destination", type=Path, help="output .wav to create")
    parser.add_argument("--channels", type=int, required=True, choices=(1, 2))
    parser.add_argument("--sample-rate", type=int, required=True)
    parser.add_argument("--frames", type=int, required=True,
                        help="exact PCM frame count the slot holds")
    parser.add_argument("--no-peak-limit", action="store_true",
                        help="do not pull peaks below full scale")
    parser.add_argument("--no-fade-on-trim", action="store_true",
                        help="cut abruptly instead of fading into a trim")
    parsed = parser.parse_args(argv)

    try:
        shape = AudioShape(
            channels=parsed.channels,
            sample_rate=parsed.sample_rate,
            frame_count=parsed.frames,
        )
        pcm, report = convert(
            parsed.source,
            shape,
            limit_peak=not parsed.no_peak_limit,
            fade_on_trim=not parsed.no_fade_on_trim,
        )
        written = write_pcm16_wav(pcm, shape, parsed.destination)
    except AudioConversionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"source: {report.source.describe()}")
    print(f"slot:   {shape.describe()}")
    for note in report.notes:
        print(f"  - {note}")
    print(f"wrote {written} ({written.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
