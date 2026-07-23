#!/usr/bin/env python3
"""Create deterministic, redistributable assets for the host-shell smoke test."""

from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def write_logo(
    path: Path, variant: str = "navy", width: int = 256, height: int = 256
) -> None:
    palettes = {
        "navy": ((225, 55, 20, 255), (18, 52, 96, 255), (8, 24, 50, 255)),
        "gold": ((25, 70, 145, 255), (245, 185, 40, 255), (90, 45, 10, 255)),
    }
    if variant not in palettes:
        raise ValueError(f"unknown logo variant: {variant}")
    if not 1 <= width <= 8192 or not 1 <= height <= 8192:
        raise ValueError("logo dimensions must be between 1 and 8192 pixels")
    accent, light, dark = palettes[variant]
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            checker = ((x // 32) + (y // 32)) & 1
            edge = x < 10 or y < 10 or x >= width - 10 or y >= height - 10
            slash = abs((x + y) - width) < 18
            if edge:
                color = (235, 238, 244, 255)
            elif slash:
                color = accent
            elif checker:
                color = light
            else:
                color = dark
            rows.extend(color)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    encoded = signature + png_chunk(b"IHDR", ihdr)
    encoded += png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
    encoded += png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(encoded)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic, redistributable host-shell logo"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/mod/common/ui/team_logo.png"),
    )
    parser.add_argument("--variant", choices=("navy", "gold"), default="navy")
    args = parser.parse_args()
    write_logo(args.output, args.variant)
    print(args.output)


if __name__ == "__main__":
    main()
