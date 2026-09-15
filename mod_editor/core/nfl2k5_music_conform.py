"""Music-only conversion: SoXR low-pass before decimation and final PCM16 TPDF.

The shared converter already used SoXR precision 28. This path tightens its
stopband with precision 33, cutoff 0.90 and Chebyshev rejection. The sweep
regression reports that small, already inaudible alias floor separately from
16-bit dither noise. No claim about Mud's listening result is made here.
"""
from __future__ import annotations

import array
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile

from .audio_conform import (AudioConformError, MusicConformReport, _convert_module,
    _pcm_samples, _pcm_bytes, music_rms, music_downmix, shape_for,
    music_quality_warnings, MUSIC_MAX_SECONDS, FFMPEG_INSTALL)

RESAMPLE_FILTER = "aresample={rate}:resampler=soxr:precision=33:cutoff=0.90:cheby=1"


class TPDFQuantizer:
    """Two independent uniforms, +/-1 LSB triangular noise before rounding.

    One generator per import, kept across chunks; repeat imports are byte
    reproducible and stereo channels receive different noise. Preserve exact
    digital zeros (including padding/fade endpoints). Saturate only at rails.
    """
    def __init__(self, seed=0x2B70):
        self.random = random.Random(seed)

    def __call__(self, samples):
        out = array.array("h")
        for value in samples:
            if not math.isfinite(value):
                raise AudioConformError("This file contains damaged sound; choose another copy.")
            noise = self.random.random() - self.random.random()
            scaled = value * 32768 + noise
            rounded = math.floor(scaled + 0.5)
            out.append(0 if value == 0 else max(-32768, min(32767, rounded)))
        if sys.byteorder != "little":
            out.byteswap()
        return out.tobytes()


def decode_music(source, shape, timeout, *, cancelled=None) -> bytes:
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

    module = _convert_module()
    channel_arguments = module._channel_arguments(source.channels, shape.channels)
    resample = RESAMPLE_FILTER.format(rate=shape.sample_rate)

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
        destination = Path(directory).resolve() / "decoded.pcm"
        command = (
            module._tool("ffmpeg"),
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
            completed = module._run_process(command, timeout=timeout, cancelled=cancelled)
        except subprocess.TimeoutExpired as exc:
            raise module.AudioConversionError("ffmpeg timed out decoding the audio") from exc
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", "replace").strip()
            last = detail.splitlines()[-1] if detail else "no diagnostic output"
            raise module.AudioConversionError(f"ffmpeg could not decode that audio: {last}")

        module._require(destination.is_file(), "ffmpeg produced no output")
        produced = destination.stat().st_size
        module._require(produced > 0, "ffmpeg produced an empty decode")
        module._require(
            produced <= module.MAX_DECODED_BYTES,
            "Decoded audio exceeds the size ceiling",
        )
        with open(destination, "rb") as handle:
            data = handle.read()
    module._require(len(data) == produced, "Decoded audio changed size while reading")
    return data


def conform_song(supplied, destination, *, reference_rms, cancelled=None):
    """Free-length song, stereo PCM16, without truncating or padding to a slot.

    Decode at most ten minutes plus the shared converter's half-second sentinel.
    Check actual frames, not MP3 container duration (which includes encoder delay).
    Float resampling precedes one gain/peak pass and one PCM quantization. Largest
    decoded buffer is about 106 MB; no disc or archive is opened here.
    """
    import array
    import json
    import math
    import wave

    def check():
        if cancelled and cancelled():
            raise AudioConformError("Music import cancelled; nothing was changed")

    check()
    if not math.isfinite(reference_rms) or reference_rms < 0:
        raise AudioConformError("The game's music volume could not be read")
    module = _convert_module()
    if module is None:
        raise AudioConformError("The audio converter is unavailable")
    source = module._open_source(supplied)
    samples = None
    rate = bits = bitrate = 0
    if source.suffix.lower() == ".wav":
        try:
            with wave.open(str(source), "rb") as wav:
                rate, bits = wav.getframerate(), wav.getsampwidth()*8
                frames, channels = wav.getnframes(), wav.getnchannels()
                if frames > MUSIC_MAX_SECONDS*rate:
                    raise AudioConformError("This song is over 10 minutes; choose a shorter copy.")
                if rate == 22050 and bits == 16 and channels in (1, 2):
                    pcm = wav.readframes(frames)
                    if len(pcm) != frames*channels*2:
                        raise AudioConformError("This song is incomplete; choose another copy.")
                    values = _pcm_samples(pcm)
                    samples = array.array("f", (v/32768 for x in values
                                               for v in ((x, x) if channels == 1 else (x,))))
        except (wave.Error, EOFError):
            pass
    if samples is None:
        if not module.ffmpeg_available():
            raise AudioConformError(FFMPEG_INSTALL)
        info = module.probe(source, cancelled=cancelled)
        rate = info.sample_rate
        result = module._run_process((module._tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=bits_per_sample,bits_per_raw_sample,bit_rate", "-of", "json", str(source)),
            timeout=module.DEFAULT_TIMEOUT_SECONDS, cancelled=cancelled)
        if result.returncode == 0:
            streams = json.loads(result.stdout).get("streams", [])
            fields = streams[0] if streams else {}
            def number(key):
                try:
                    return int(fields.get(key, 0))
                except (ValueError, TypeError):
                    return 0
            bits = bits or number("bits_per_raw_sample") or number("bits_per_sample")
            bitrate = number("bit_rate")
        decoded = decode_music(info, shape_for(2, 22050, MUSIC_MAX_SECONDS*22050),
                                 module.DEFAULT_TIMEOUT_SECONDS, cancelled=cancelled)
        if len(decoded) % 8:
            raise AudioConformError("This song is incomplete; choose another copy.")
        samples = array.array("f", decoded)
        del decoded
        if sys.byteorder != "little":
            samples.byteswap()
    check()
    frames = len(samples)//2
    if not frames:
        raise AudioConformError("This file has no sound; choose another copy.")
    if frames > MUSIC_MAX_SECONDS*22050:
        raise AudioConformError("This song is over 10 minutes; choose a shorter copy.")
    if any(not math.isfinite(v) for v in samples):
        raise AudioConformError("This file contains damaged sound; choose another copy.")
    rms = math.sqrt(sum(v*v for v in samples)/len(samples))
    wanted = reference_rms/rms if rms > 1/32768 and reference_rms > 1/32768 else 1.0
    capped = wanted > 10**(12/20)
    peak = max(abs(v) for v in samples)
    gain = min(wanted, 10**(12/20), 10**(-1/20)/peak if peak else 1.0)
    for i in range(len(samples)):
        if i % 32768 == 0:
            check()
        samples[i] *= gain
    quantize = TPDFQuantizer()
    # Quantize in bounded chunks so cancellation remains responsive.
    with wave.open(str(destination), "wb") as wav:
        wav.setparams((2, 2, 22050, frames, "NONE", "not compressed"))
        for i in range(0, len(samples), 32768):
            check()
            wav.writeframesraw(quantize(samples[i:i+32768]))
    check()
    notes = music_quality_warnings(sample_rate=rate, bits=bits, bit_rate=bitrate,
                                   gain_capped=capped or (rms <= 1/32768 and reference_rms > 1/32768))
    return dict(seconds=frames/22050, frames=frames, sample_rate=rate, bits=bits,
                bit_rate=bitrate, input_rms=rms, reference_rms=reference_rms,
                gain_db=20*math.log10(gain), gain_capped=capped, notes=list(notes))


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
        info = module.probe(source, cancelled=cancelled)
        decoded = decode_music(info, shape, module.DEFAULT_TIMEOUT_SECONDS, cancelled=cancelled)
        if len(decoded) % (4*shape.channels):
            raise AudioConformError("Music decode contains an incomplete frame")
        samples = array.array("f", decoded)
        if sys.byteorder != "little":
            samples.byteswap()
        seconds = info.duration_seconds
        supplied_frames = max(1, round(seconds*shape.sample_rate))
        useful = min(shape.frame_count, len(samples)//shape.channels)
        samples = samples[:useful*shape.channels]
    else:
        pcm, supplied_frames = native
        seconds = supplied_frames/shape.sample_rate
        useful = min(shape.frame_count, supplied_frames)
        samples = array.array("f", (v/32768 for v in _pcm_samples(pcm[:useful*shape.channels*2])))
    check()
    if any(not math.isfinite(v) for v in samples):
        raise AudioConformError("This file contains damaged sound; choose another copy.")
    input_rms = math.sqrt(sum(v*v for v in samples)/len(samples)) if samples else 0
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
    peak = max((abs(x) for x in samples), default=0)
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
        samples[i] = sample*scale
    quantize = TPDFQuantizer()
    chunks = []
    for i in range(0, len(samples), 32768):
        check()
        chunk = samples[i:i+32768]
        # A native PCM16 input at unity gain needs no new quantization noise.
        chunks.append(_pcm_bytes(array.array("h", (round(v*32768) for v in chunk)))
                      if native is not None and gain == 1 and not fade else quantize(chunk))
    output = b"".join(chunks)
    output_rms = music_rms(output)
    output += bytes((shape.frame_count-useful)*shape.channels*2)
    check()
    return output, MusicConformReport(
        seconds, shape.duration_seconds, trimmed/shape.sample_rate,
        max(0, shape.frame_count-useful)/shape.sample_rate, fade/shape.sample_rate,
        baseline, input_rms, output_rms, 20*math.log10(gain),
        limited or converter_limited, gain_capped, match_volume, tuple(notes))
