"""Synthetic MPEG-1 video / ADX elementary streams for the Sofdec tests. No game data.

The video is structurally exact (sequence, GOP, picture and slice start codes in
ffmpeg's open-GOP shape with 30-picture time codes) but its slices are filler,
so it is for the muxer and archive tests, not for a decoder.
"""
from __future__ import annotations

import random
import struct

from mod_editor.core import nfl2k5_sofdec as sofdec


def sequence_header(width=640, height=480, *, aspect=12, rate=4, bit_rate=0x3FFFF, vbv=112):
    word = bit_rate << 14 | 1 << 13 | vbv << 3
    return (b"\0\0\1\xb3" + bytes((width >> 4, (width & 15) << 4 | height >> 8, height & 0xFF, aspect << 4 | rate))
            + word.to_bytes(4, "big"))


def gop_header(first_display, *, closed, drop=False):
    seconds, pictures = divmod(first_display, 30)
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    word = (int(drop) << 31 | hours << 26 | minutes << 20 | 1 << 19 | seconds << 13 | pictures << 7
            | int(closed) << 6)
    return b"\0\0\1\xb8" + word.to_bytes(4, "big")


def picture_header(temporal, kind, vbv_delay=0xFFFF):
    word = temporal << 22 | "_IPB".index(kind) << 19 | vbv_delay << 3
    return b"\0\0\1\x00" + word.to_bytes(4, "big") + b"\x88"


def gop_pattern(first):
    """Coded (kind, temporal reference) of one GOP in ffmpeg's -g 15 -bf 2 shape."""
    if first:   # closed: I0 P3 B1 B2 ... P12 B10 B11 (13 pictures)
        return [("I", 0)] + [x for p in range(3, 13, 3) for x in (("P", p), ("B", p - 2), ("B", p - 1))]
    return ([("I", 2), ("B", 0), ("B", 1)] +
            [x for p in range(5, 15, 3) for x in (("P", p), ("B", p - 2), ("B", p - 1))])


def synthetic_video(gops=4, *, width=640, height=480, seed=5, slice_bytes=(900, 400, 150),
                    repeat_headers=False, end_code=True, vbv_delay=0xFFFF, header=None, drop=False,
                    first_closed=True):
    """13 + 15 x (gops - 1) pictures; I/P/B slices of about ``slice_bytes`` filler bytes."""
    rng = random.Random(seed)
    head = header or sequence_header(width, height)
    out, display = bytearray(head), 0
    for g in range(gops):
        if g and repeat_headers:
            out += head
        out += gop_header(display, closed=first_closed if g == 0 else False, drop=drop)
        pattern = gop_pattern(g == 0)
        for kind, temporal in pattern:
            out += picture_header(temporal, kind, vbv_delay)
            size = slice_bytes["IPB".index(kind)]
            for row in range(1, height // 16 + 1):
                out += b"\0\0\1" + bytes((row,)) + bytes(rng.randrange(1, 256) for _ in range(size // 30 + 1))
        display += len(pattern)
    if end_code:
        out += b"\0\0\1\xb7"
    return bytes(out)


def synthetic_adx(samples=96000, *, channels=2, rate=48000, seed=9, version=3):
    """ffmpeg-style ADX: the 36-byte version-3 header, 18-byte blocks, the end block."""
    rng = random.Random(seed)
    header = (b"\x80\x00\x00\x20" + bytes((3, 18, 4, channels)) + struct.pack(">II", rate, samples)
              + struct.pack(">H", 500) + bytes((version, 0))).ljust(0x1E, b"\0") + b"(c)CRI"
    frames = -(-samples // 32)
    blocks = bytearray()
    for _ in range(frames * channels):
        blocks += struct.pack(">H", rng.randrange(1, 0x0400)) + bytes(rng.randrange(256) for _ in range(16))
    return header + bytes(blocks) + sofdec.ADX_END


def synthetic_movie(gops=4, *, seconds=None, **video):
    es = sofdec.conform_video(synthetic_video(gops, **video))[0]   # as the encoder does
    pictures = 13 + 15 * (gops - 1)
    samples = round((seconds or pictures * 1001 / 30000) * 48000)
    return sofdec.mux(es, synthetic_adx(samples)), es
