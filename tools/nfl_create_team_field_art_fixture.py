#!/usr/bin/env python3
"""Create the deterministic non-retail 256x128 field-art proof PNG."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from nfl_txtr import encode_rgba_png


WIDTH = 256
HEIGHT = 128


def fixture_rgba() -> bytes:
    rgba = bytearray(WIDTH * HEIGHT * 4)
    colors = ((0x00, 0xF0, 0xFF, 0xFF), (0xFF, 0x00, 0xB8, 0xFF),
              (0x18, 0x18, 0x20, 0xFF), (0xFF, 0xE6, 0x00, 0xFF))
    for y in range(HEIGHT):
        for x in range(WIDTH):
            tile = ((x // 16) ^ (y // 16)) & 1
            color = colors[tile]
            if abs((x * HEIGHT // WIDTH) - y) <= 3 or abs((WIDTH - 1 - x) *
                                                          HEIGHT // WIDTH - y) <= 3:
                color = colors[3]
            if 48 <= y < 80 and 36 <= x < 220:
                color = colors[2] if ((x // 8) + (y // 8)) & 1 else colors[3]
            offset = (y * WIDTH + x) * 4
            rgba[offset:offset + 4] = bytes(color)
    return bytes(rgba)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        parent = args.output.parent.resolve(strict=True)
        target = parent / args.output.name
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                             getattr(os, "O_NOFOLLOW", 0) |
                             getattr(os, "O_CLOEXEC", 0), 0o644)
        payload = encode_rgba_png(WIDTH, HEIGHT, fixture_rgba())
        try:
            position = 0
            while position < len(payload):
                amount = os.write(descriptor, payload[position:])
                if amount <= 0:
                    raise OSError("short fixture write")
                position += amount
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        print(f"NFL_CREATE_TEAM_FIELD_ART_FIXTURE_OK path={target} bytes={len(payload)}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
