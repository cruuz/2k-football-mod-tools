#!/usr/bin/env python3
"""Create a deterministic non-retail 256x256 live-helmet diagnostic PNG."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys

from nfl_txtr import encode_rgba_png


GLYPHS = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "0": (14, 17, 19, 21, 25, 17, 14), "2": (14, 17, 1, 2, 4, 8, 31),
    "3": (30, 1, 1, 14, 1, 1, 30), "A": (14, 17, 17, 31, 17, 17, 17),
    "C": (14, 17, 16, 16, 16, 17, 14), "D": (30, 17, 17, 17, 17, 17, 30),
    "E": (31, 16, 16, 30, 16, 16, 31), "I": (31, 4, 4, 4, 4, 4, 31),
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


def draw_text(image: bytearray, text: str, x: int, y: int, scale: int,
              color: tuple[int, int, int, int]) -> None:
    for character in text:
        rows = GLYPHS[character]
        for row, bits in enumerate(rows):
            for column in range(5):
                if bits & (1 << (4 - column)):
                    for dy in range(scale):
                        for dx in range(scale):
                            px = x + column * scale + dx
                            py = y + row * scale + dy
                            offset = (py * 256 + px) * 4
                            image[offset:offset + 4] = bytes(color)
        x += 6 * scale


def build() -> bytes:
    colors = (
        (255, 0, 255, 255), (0, 255, 255, 255),
        (0, 255, 64, 255), (255, 224, 0, 255),
    )
    rgba = bytearray(256 * 256 * 4)
    for y in range(256):
        for x in range(256):
            quadrant = (x >= 128) + 2 * (y >= 128)
            color = colors[quadrant]
            if ((x // 16) ^ (y // 16)) & 1:
                color = tuple(max(0, channel - 48) for channel in color[:3]) + (255,)
            if x < 8 or y < 8 or x >= 248 or y >= 248 or abs(x - y) < 3:
                color = (0, 0, 0, 255)
            offset = (y * 256 + x) * 4
            rgba[offset:offset + 4] = bytes(color)
    for top in (54, 118, 182):
        for y in range(top, top + 30):
            for x in range(22, 234):
                offset = (y * 256 + x) * 4
                rgba[offset:offset + 4] = b"\x00\x00\x00\xff"
    draw_text(rgba, "LIVE 3D", 43, 60, 3, (255, 255, 255, 255))
    draw_text(rgba, "NOT CARD", 31, 124, 3, (255, 255, 255, 255))
    draw_text(rgba, "CODEX", 70, 188, 3, (255, 255, 255, 255))
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
        descriptor = os.open(
            target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
            getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o644)
        identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
        success = False
        try:
            payload = build()
            offset = 0
            while offset < len(payload):
                amount = os.write(descriptor, payload[offset:])
                require(amount > 0, "short fixture write")
                offset += amount
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
            "NFL_LIVE_HELMET_TXTR_FIXTURE_OK "
            f"path={target} size={len(payload)} sha256={hashlib.sha256(payload).hexdigest()}"
        )
        return 0
    except (FixtureError, OSError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
