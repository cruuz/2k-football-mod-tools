#!/usr/bin/env python3
"""Create a deterministic non-retail 256x256 live-face diagnostic PNG."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys

from nfl_txtr import encode_rgba_png


GLYPHS = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "A": (14, 17, 17, 31, 17, 17, 17), "C": (14, 17, 16, 16, 16, 17, 14),
    "D": (30, 17, 17, 17, 17, 17, 30), "E": (31, 16, 16, 30, 16, 16, 31),
    "F": (31, 16, 16, 30, 16, 16, 16), "I": (31, 4, 4, 4, 4, 4, 31),
    "L": (16, 16, 16, 16, 16, 16, 31), "N": (17, 25, 25, 21, 19, 19, 17),
    "O": (14, 17, 17, 17, 17, 17, 14), "R": (30, 17, 17, 30, 20, 18, 17),
    "T": (31, 4, 4, 4, 4, 4, 4), "V": (17, 17, 17, 17, 17, 10, 4),
    "X": (17, 17, 10, 4, 10, 17, 17),
}


class FixtureError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def draw_text(image: bytearray, text: str, x: int, y: int, scale: int) -> None:
    for character in text:
        rows = GLYPHS[character]
        for row, bits in enumerate(rows):
            for column in range(5):
                if bits & (1 << (4 - column)):
                    for dy in range(scale):
                        for dx in range(scale):
                            offset = ((y + row * scale + dy) * 256 +
                                      x + column * scale + dx) * 4
                            image[offset:offset + 4] = b"\xff\xff\xff\xff"
        x += 6 * scale


def build() -> bytes:
    rgba = bytearray(256 * 256 * 4)
    palette = ((255, 32, 96, 255), (32, 224, 255, 255),
               (64, 255, 96, 255), (255, 208, 32, 255))
    for y in range(256):
        for x in range(256):
            color = palette[(x >= 128) + 2 * (y >= 128)]
            if ((x // 16) ^ (y // 16)) & 1:
                color = tuple(max(0, value - 48) for value in color[:3]) + (255,)
            if x < 8 or y < 8 or x >= 248 or y >= 248 or abs(x + y - 255) < 3:
                color = (0, 0, 0, 255)
            offset = (y * 256 + x) * 4
            rgba[offset:offset + 4] = bytes(color)
    for top in (48, 112, 176):
        for y in range(top, top + 32):
            for x in range(16, 240):
                offset = (y * 256 + x) * 4
                rgba[offset:offset + 4] = b"\0\0\0\xff"
    draw_text(rgba, "LIVE FACE", 34, 54, 3)
    draw_text(rgba, "NOT RETAIL", 25, 118, 3)
    draw_text(rgba, "CODEX", 70, 182, 3)
    payload = encode_rgba_png(256, 256, bytes(rgba))
    require(payload.startswith(b"\x89PNG\r\n\x1a\n"), "PNG encoding failed")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        parent = args.output.parent.resolve(strict=True)
        target = parent / args.output.name
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, "O_NOFOLLOW", 0) |
                             getattr(os, "O_CLOEXEC", 0), 0o644)
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        success = False
        try:
            payload = build()
            position = 0
            while position < len(payload):
                amount = os.write(descriptor, payload[position:])
                require(amount > 0, "short fixture write")
                position += amount
            os.fsync(descriptor)
            current = target.stat(follow_symlinks=False)
            require((current.st_dev, current.st_ino, current.st_size) ==
                    (identity[0], identity[1], len(payload)),
                    "fixture output pathname changed")
            success = True
        finally:
            os.close(descriptor)
            if not success:
                try:
                    current = target.stat(follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == identity:
                        target.unlink()
                except FileNotFoundError:
                    pass
        print(
            "NFL_LIVE_FACE_TEXTURE_FIXTURE_OK "
            f"path={target} size={len(payload)} sha256={hashlib.sha256(payload).hexdigest()}"
        )
        return 0
    except (FixtureError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
