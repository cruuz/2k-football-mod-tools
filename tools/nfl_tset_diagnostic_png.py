#!/usr/bin/env python3
"""Generate a conspicuous, highly compressible 512x256 RGBA test jersey."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys

from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import encode_rgba_png


WIDTH = 512
HEIGHT = 256
OUTPUT_NAME = "nfl2k5_lions_diagnostic_codex_mod.png"
GLYPHS = {
    "C": ("11111", "10000", "10000", "10000", "10000", "10000", "11111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
}


def build_rgba() -> bytes:
    colors = {
        "magenta": (255, 0, 255, 255),
        "cyan": (0, 255, 255, 255),
        "yellow": (255, 255, 0, 255),
        "black": (0, 0, 0, 255),
        "white": (255, 255, 255, 255),
        "green": (0, 255, 0, 255),
        "red": (255, 0, 0, 255),
    }
    pixels = bytearray(WIDTH * HEIGHT * 4)

    def put(x: int, y: int, color: tuple[int, int, int, int]) -> None:
        offset = (y * WIDTH + x) * 4
        pixels[offset:offset + 4] = bytes(color)

    def rectangle(x0: int, y0: int, x1: int, y1: int,
                  color: tuple[int, int, int, int]) -> None:
        for y in range(max(0, y0), min(HEIGHT, y1)):
            for x in range(max(0, x0), min(WIDTH, x1)):
                put(x, y, color)

    for y in range(HEIGHT):
        for x in range(WIDTH):
            checker = ((x // 32) + (y // 32)) & 1
            put(x, y, colors["magenta"] if checker == 0 else colors["cyan"])
    rectangle(0, 0, WIDTH, 16, colors["yellow"])
    rectangle(0, HEIGHT - 16, WIDTH, HEIGHT, colors["yellow"])
    rectangle(0, 0, 16, HEIGHT, colors["yellow"])
    rectangle(WIDTH - 16, 0, WIDTH, HEIGHT, colors["yellow"])
    rectangle(32, 72, WIDTH - 32, 184, colors["black"])
    rectangle(32, 72, WIDTH - 32, 80, colors["green"])
    rectangle(32, 176, WIDTH - 32, 184, colors["green"])
    rectangle(16, 16, 80, 48, colors["red"])
    rectangle(WIDTH - 80, HEIGHT - 48, WIDTH - 16, HEIGHT - 16, colors["red"])

    text = "CODEX MOD"
    scale = 8
    advance = 6 * scale
    text_width = len(text) * advance - scale
    start_x = (WIDTH - text_width) // 2
    start_y = 96
    for character_index, character in enumerate(text):
        if character == " ":
            continue
        glyph = GLYPHS[character]
        origin_x = start_x + character_index * advance
        for row, bits in enumerate(glyph):
            for column, bit in enumerate(bits):
                if bit == "1":
                    rectangle(
                        origin_x + column * scale,
                        start_y + row * scale,
                        origin_x + (column + 1) * scale,
                        start_y + (row + 1) * scale,
                        colors["white"],
                    )
    return bytes(pixels)


def run(output: Path) -> str:
    if output.name != OUTPUT_NAME:
        raise ValueError(f"diagnostic output must be named {OUTPUT_NAME}")
    parent = output.parent.resolve(strict=True)
    target = parent / output.name
    rgba = build_rgba()
    payload = encode_rgba_png(WIDTH, HEIGHT, rgba)
    descriptor = os.open(
        target,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
        0o644,
    )
    success = False
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            if written <= 0:
                raise OSError("short diagnostic PNG write")
            position += written
        os.fsync(descriptor)
        width, height, decoded = decode_rgba_png(payload)
        if (width, height, decoded) != (WIDTH, HEIGHT, rgba):
            raise ValueError("diagnostic PNG strict round trip failed")
        success = True
    finally:
        os.close(descriptor)
        if not success:
            try:
                target.unlink()
            except FileNotFoundError:
                pass
    return hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        digest = run(args.output)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"NFL_TSET_DIAGNOSTIC_PNG_OK sha256={digest} size={WIDTH}x{HEIGHT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
