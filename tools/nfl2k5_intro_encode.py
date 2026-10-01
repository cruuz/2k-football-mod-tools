#!/usr/bin/env python3
"""Make a game intro movie (a CRI Sofdec ``.mov``) from any video clip, offline. EXPERIMENTAL / UNWITNESSED.

    python3 tools/nfl2k5_intro_encode.py clip.mp4 --in 0 --out 14 --audio-track 0 --fit letterbox -o intro.mov

ffmpeg makes the two elementary streams: MPEG-1 video, 640x480 at 29.97 in the
retail GOP shape (15 pictures, two B pictures between anchors, open GOPs after a
closed first one, no picture above the largest retail picture), and 48 kHz stereo
CRI ADX, loudness-matched to the retail intro by default.  ``nfl2k5_sofdec`` then
gives the video the retail sequence-level form and muxes both by CRI's SFM 2.21
rules, which it reproduces byte for byte on all 29 retail ADX streams.

Checks on the result: the retail muxing rules (``nfl2k5_sofdec.problems``); a
decode round trip (ffmpeg decodes the movie, and its video and audio frames hash
identically to the decode of the elementary streams that went in, with the right
picture count and size); and, when unicorn and the pinned retail XBE are present,
the game's own header-stage code accepts the file with the retail intro's reads
and its 10,171,344-byte allocation.  Whether the game plays it is UNWITNESSED:
load the movie with Build > Custom intro video and watch the boot in xemu.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_sofdec as sofdec  # noqa: E402

SCHEMA = "nfl2k5_intro_encode/v1"
FITS = ("letterbox", "anamorphic", "crop")
RETAIL_INTRO_LUFS = -14.1       # integrated loudness of the retail intro.mov audio (ffmpeg ebur128)
TRUE_PEAK = -1.5                # dBTP ceiling for the loudness match
MAX_SECONDS = 180.0             # the retail intro runs 64.6 s; the Build grows or shrinks the archive either way
DEFAULT_KBPS = 5000             # retail 640x480 streams average 4.0 to 5.7 Mbit/s
VBV_BITS = 1000000              # keeps every picture under the 128,865-byte retail maximum
MOVIE_NAME = "intro.mov"


class EncodeError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise EncodeError(message)


def seconds(text):
    """Seconds from ``12.5``, ``1:02.5`` or ``0:01:02.5``."""
    value = str(text).strip()
    require(re.fullmatch(r"\d+(\.\d+)?|(\d+:){1,2}\d+(\.\d+)?", value) is not None, f"not a time: {text}")
    total = 0.0
    for part in value.split(":"):
        total = total * 60 + float(part)
    return total


def tool(name, explicit=None):
    found = explicit or shutil.which(name)
    require(found is not None, f"{name} was not found. Install FFmpeg (6.x) and put it on PATH, or pass --{name}.")
    return str(found)


def run(command, *, timeout=1800):
    done = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    if done.returncode != 0:
        tail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-6:]
        raise EncodeError(f"{Path(command[0]).name} failed: " + " | ".join(tail))
    return done


def file_sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def probe(ffprobe, clip):
    done = run([ffprobe, "-v", "error", "-show_entries",
                "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
                "-of", "json", str(clip)])
    info = json.loads(done.stdout)
    streams = info.get("streams", [])
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    require(video, "the clip has no video stream")
    duration = float(info.get("format", {}).get("duration") or 0)
    require(duration > 0, "the clip has no readable duration")
    return dict(duration=duration, video=video[0], audio=audio)


def video_filter(fit, source_width, source_height):
    base = "fps=30000/1001"
    if fit == "anamorphic":      # the whole picture squeezed into 640x480: right on a 16:9 display
        shape = "scale=640:480:flags=lanczos"
    elif fit == "crop":          # the centre 4:3 of the picture
        shape = "crop='min(iw,ih*4/3)':'min(ih,iw*3/4)',scale=640:480:flags=lanczos"
    else:                        # the whole picture at its own shape, black bars: right on a 4:3 display
        shape = ("scale=640:480:force_original_aspect_ratio=decrease:flags=lanczos,"
                 "scale=trunc(iw/2)*2:trunc(ih/2)*2,pad=640:480:(ow-iw)/2:(oh-ih)/2:black")
    return f"{base},{shape},setsar=1,format=yuv420p"


def loudness_filter(ffmpeg, clip, start, length, track, target):
    """Two-pass EBU R128 match: measure, then one linear gain when the peak allows it."""
    base = f"loudnorm=I={target}:TP={TRUE_PEAK}:LRA=11"
    done = run([ffmpeg, "-hide_banner", "-nostats", "-ss", f"{start:.6f}", "-t", f"{length:.6f}", "-i", str(clip),
                "-map", f"0:a:{track}", "-af", base + ":print_format=json", "-f", "null", "-"])
    text = done.stderr.decode("utf-8", "replace")
    found = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", text, re.S)
    require(found is not None, "loudness measurement failed")
    m = json.loads(found.group(0))
    if m["input_i"] in ("-inf", "inf") or float(m["input_i"]) < -70:
        return None, dict(measured="silent", applied="none")
    chain = (f"{base}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
             f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    return chain, dict(measured_lufs=float(m["input_i"]), measured_true_peak=float(m["input_tp"]),
                       target_lufs=target, true_peak_ceiling=TRUE_PEAK)


def framemd5(ffmpeg, path, selector):
    """One hash per decoded picture."""
    done = run([ffmpeg, "-v", "error", "-i", str(path), "-map", selector, "-f", "framemd5", "-"])
    rows = [line for line in done.stdout.decode("ascii", "replace").splitlines() if line and not line.startswith("#")]
    return [line.rsplit(",", 1)[-1].strip() for line in rows]


def pcm(ffmpeg, path):
    """The whole decoded audio as 16-bit stereo PCM: (sha256, stereo samples)."""
    done = run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a:0", "-f", "s16le", "-ac", "2", "-"])
    return hashlib.sha256(done.stdout).hexdigest(), len(done.stdout) // 4


def native_header_check(movie):
    """The retail header-stage code on this file (unicorn + pinned retail XBE), else a reason it was skipped."""
    try:
        import unicorn  # noqa: F401
        from tests.nfl2k5_my_career_fixture import XBE
        from tests.nfl2k5_movie_native import MovieMachine
        from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
    except ImportError as exc:
        return dict(status="skipped", reason=f"native harness unavailable ({exc.name})")
    if not XBE.is_file():
        return dict(status="skipped", reason="pinned USA retail default.xbe not found")
    retail = XBE.read_bytes()
    if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
        return dict(status="skipped", reason="default.xbe differs from the USA evidence pin")
    machine = MovieMachine(retail)
    machine.uc.mem_write(machine.SAVE, "intro\0".encode("utf-16le"))
    machine.files[MOVIE_NAME] = lambda at, n: movie[at:at + n] if at + n <= len(movie) else b""
    returned = machine.call(0x178150, ecx=machine.SAVE, args=(0,), budget=100000)
    reads = [list(r) for r in machine.reads]
    ok = (machine.allocations_seen == [sofdec.BOOT_ALLOCATION] and
          [tuple(r) for r in reads] == list(sofdec.HEADER_STAGE_READS) and returned == 0)
    return dict(status="accepted" if ok else "rejected", reads=reads, allocation_requests=machine.allocations_seen,
                expected_allocation=sofdec.BOOT_ALLOCATION,
                note="Retail code 0x178150 -> 0x3CB940/0x3CB8B0/0x3CB750 and sizing; the harness fails the "
                     "allocation on purpose, so no decoder ran.")


def encode(clip, output, *, start=0.0, end=None, audio_track="auto", fit="letterbox", kbps=DEFAULT_KBPS,
           loudness=RETAIL_INTRO_LUFS, ffmpeg=None, ffprobe=None, native=True, progress=print):
    clip, output = Path(clip).resolve(), Path(output).absolute()
    require(clip.is_file(), f"clip not found: {clip}")
    require(fit in FITS, f"fit must be one of {', '.join(FITS)}")
    require(1000 <= int(kbps) <= 8000, "video bitrate must be 1000..8000 kbit/s")
    require(output.parent.is_dir(), f"output folder does not exist: {output.parent}")
    require(output != clip, "output would overwrite the clip")
    ffmpeg, ffprobe = tool("ffmpeg", ffmpeg), tool("ffprobe", ffprobe)
    info = probe(ffprobe, clip)
    end = info["duration"] if end is None else float(end)
    start = float(start)
    require(0 <= start < end <= info["duration"] + 0.05, f"in/out must satisfy 0 <= in < out <= {info['duration']:.3f}")
    length = end - start
    require(length <= MAX_SECONDS, f"intro is limited to {MAX_SECONDS:.0f} seconds")
    tracks = len(info["audio"])
    if audio_track == "auto":            # the first audio track, or silence for a clip without audio
        audio_track = 0 if tracks else None
    require(audio_track is None or 0 <= audio_track < tracks,
            f"audio track {audio_track} does not exist (the clip has {tracks}); use --audio-track none for silence")
    receipt = dict(schema=SCHEMA, experimental=True, runtime_witnessed=False,
                   input=dict(clip=str(clip), sha256=file_sha256(clip), duration=info["duration"],
                              video=info["video"], audio_tracks=tracks),
                   settings=dict(start=start, end=end, seconds=round(length, 6), audio_track=audio_track, fit=fit,
                                 video_kbps=int(kbps), vbv_bits=VBV_BITS, loudness=loudness),
                   ffmpeg=run([ffmpeg, "-version"]).stdout.decode("utf-8", "replace").splitlines()[0])
    with tempfile.TemporaryDirectory(prefix="intro-encode-") as temp:
        temp = Path(temp)
        es_path, adx_path = temp / "video.m1v", temp / "audio.adx"
        progress("Encoding MPEG-1 video")
        video_cmd = [ffmpeg, "-v", "error", "-y", "-ss", f"{start:.6f}", "-t", f"{length:.6f}", "-i", str(clip),
                     "-map", "0:v:0", "-an", "-vf", video_filter(fit, info["video"].get("width"), info["video"].get("height")),
                     "-c:v", "mpeg1video", "-b:v", f"{int(kbps)}k", "-maxrate", "8000k", "-bufsize", str(VBV_BITS),
                     "-g", "15", "-bf", "2", "-mbd", "rd", "-trellis", "1", "-pix_fmt", "yuv420p",
                     "-f", "mpeg1video", str(es_path)]
        run(video_cmd)
        progress("Encoding ADX audio")
        if audio_track is None:
            audio_cmd = [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                         "-t", f"{length:.6f}", "-c:a", "adpcm_adx", "-ar", "48000", "-ac", "2", "-f", "adx", str(adx_path)]
            receipt["loudness"] = dict(applied="silence")
        else:
            chain, facts = (None, dict(applied="off")) if loudness is None else \
                loudness_filter(ffmpeg, clip, start, length, audio_track, loudness)
            receipt["loudness"] = facts
            filters = ",".join(x for x in (chain, "aresample=48000", f"apad,atrim=0:{length:.6f}") if x)
            audio_cmd = [ffmpeg, "-v", "error", "-y", "-ss", f"{start:.6f}", "-t", f"{length:.6f}", "-i", str(clip),
                         "-map", f"0:a:{audio_track}", "-vn", "-af", filters, "-c:a", "adpcm_adx", "-ar", "48000",
                         "-ac", "2", "-f", "adx", str(adx_path)]
        run(audio_cmd)
        receipt["commands"] = dict(video=[str(c) for c in video_cmd[1:]], audio=[str(c) for c in audio_cmd[1:]])
        progress("Muxing the Sofdec stream")
        conformed, conform_receipt = sofdec.conform_video(es_path.read_bytes())
        (temp / "conformed.m1v").write_bytes(conformed)
        movie = sofdec.mux(conformed, adx_path.read_bytes(), name=MOVIE_NAME)
        progress("Checking the retail rules")
        found = sofdec.problems(movie)
        require(not found, "the movie breaks a retail rule: " + "; ".join(found))
        facts = sofdec.summary(movie)
        progress("Decode round trip")
        staged = temp / MOVIE_NAME
        staged.write_bytes(movie)
        decoded_video = framemd5(ffmpeg, staged, "0:v:0")
        reference_video = framemd5(ffmpeg, temp / "conformed.m1v", "0:v:0")
        decoded_audio = pcm(ffmpeg, staged)
        reference_audio = pcm(ffmpeg, adx_path)
        shape = json.loads(run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                "stream=codec_name,width,height", "-of", "json", str(staged)]).stdout)["streams"][0]
        round_trip = dict(video_frames=len(decoded_video), video_frames_expected=facts["pictures"],
                          video_frames_identical=decoded_video == reference_video,
                          audio_samples=decoded_audio[1], audio_samples_header=facts["audio_samples"],
                          audio_pcm_identical=decoded_audio == reference_audio,
                          decoder_sees=shape)
        require(round_trip["video_frames_identical"] and len(decoded_video) == facts["pictures"],
                "decode round trip: the movie's video does not decode to the pictures that went in")
        require(round_trip["audio_pcm_identical"] and decoded_audio[1] >= facts["audio_samples"],
                "decode round trip: the movie's audio does not decode to the samples that went in")
        require((shape.get("codec_name"), shape.get("width"), shape.get("height")) == ("mpeg1video", 640, 480),
                "decode round trip: ffmpeg does not see 640x480 MPEG-1 video")
        native_result = native_header_check(movie) if native else dict(status="skipped", reason="--no-native")
        require(native_result["status"] != "rejected", "the retail header-stage code rejects this movie")
        tmp_out = output.with_name(output.name + ".partial")
        tmp_out.write_bytes(movie)
        os.replace(tmp_out, output)
    receipt.update(conform=conform_receipt, movie=facts, output=str(output), retail_rules="pass",
                   decode_round_trip=round_trip, native_header_stage=native_result,
                   use="Build > Custom intro video (EXPERIMENTAL). The game playing it is UNWITNESSED.")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("clip", type=Path, help="any video ffmpeg reads (mp4, mkv, mov, ...)")
    parser.add_argument("--in", dest="start", default="0", help="start time in the clip (seconds or m:ss.x)")
    parser.add_argument("--out", dest="end", default=None, help="end time in the clip (default: the clip's end)")
    parser.add_argument("--audio-track", default="auto",
                        help="audio stream number among the clip's audio streams (0 = first), 'none' for silence, "
                             "or 'auto' (default: the first audio stream, silence when the clip has none)")
    parser.add_argument("--fit", choices=FITS, default="letterbox",
                        help="letterbox (4:3 display), anamorphic (16:9 display), or crop to the centre 4:3")
    parser.add_argument("--video-bitrate", type=int, default=DEFAULT_KBPS, help="average kbit/s (1000..8000)")
    parser.add_argument("--loudness", default=str(RETAIL_INTRO_LUFS),
                        help="integrated LUFS target (default: the retail intro's -14.1), or 'off'")
    parser.add_argument("-o", "--output", type=Path, default=None, help="movie to write (default: <clip>.intro.mov)")
    parser.add_argument("--receipt", type=Path, default=None, help="JSON receipt (default: <output>.json)")
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--ffprobe", default=None)
    parser.add_argument("--no-native", action="store_true", help="skip the retail header-stage check")
    args = parser.parse_args(argv)
    output = args.output or args.clip.with_name(args.clip.stem + ".intro.mov")
    choice = str(args.audio_track).lower()
    track = None if choice == "none" else "auto" if choice == "auto" else int(choice)
    loudness = None if str(args.loudness).lower() == "off" else float(args.loudness)
    try:
        receipt = encode(args.clip, output, start=seconds(args.start),
                         end=None if args.end is None else seconds(args.end), audio_track=track, fit=args.fit,
                         kbps=args.video_bitrate, loudness=loudness, ffmpeg=args.ffmpeg, ffprobe=args.ffprobe,
                         native=not args.no_native, progress=lambda text: print(text, file=sys.stderr))
    except (EncodeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"intro encode failed: {exc}", file=sys.stderr)
        return 1
    receipt_path = args.receipt or output.with_name(output.name + ".json")
    receipt_path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8", newline="\n")
    m = receipt["movie"]
    print(f"{output}: {m['bytes']:,} bytes, {m['pictures']} pictures ({m['seconds']} s), "
          f"sha256 {m['sha256']}; native header stage: {receipt['native_header_stage']['status']}")
    print(f"receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
