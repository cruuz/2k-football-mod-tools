#!/usr/bin/env python3
"""Create a deterministic non-retail NFL 2K5 portrait proof fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from nfl_txtr import encode_rgba_png


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def rgba_fixture() -> bytes:
    width = height = 128
    output = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            cell = ((x // 8) ^ (y // 8) ^ ((x + 2 * y) // 16)) & 15
            red = (cell * 47 + 23) & 255
            green = (cell * 83 + 197) & 255
            blue = (cell * 31 + 91) & 255
            alpha = (64, 128, 192, 255)[((x // 16) + (y // 16)) & 3]
            dx = x - 64
            dy = y - 57
            if dx * dx + dy * dy < 40 * 40:
                red, green, blue, alpha = ((255, 0, 203, 255)
                                           if ((x // 6 + y // 6) & 1)
                                           else (0, 239, 255, 255))
            if 18 <= y < 24 or 102 <= y < 108 or 12 <= x < 18 or 110 <= x < 116:
                red, green, blue, alpha = 255, 255, 0, 255
            offset = (y * width + x) * 4
            output[offset:offset + 4] = bytes((red, green, blue, alpha))
    return bytes(output)


def exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0), 0o644)
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            if written <= 0:
                raise OSError("short portrait fixture write")
            position += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    directory = args.output_dir.resolve(strict=False)
    directory.mkdir(parents=True, exist_ok=True)
    rgba = rgba_fixture()
    png = encode_rgba_png(128, 128, rgba)
    name = "portrait_0124_nonretail.png"
    exclusive(directory / name, png)
    plan = {
        "schema": "nfl2k5_player_portrait_plan/v1",
        "purpose": "deterministic non-retail numeric roster portrait copy-only proof",
        "edits": [{"portrait_id": "0124", "png": str(directory / name)}],
    }
    report = {
        "schema": "nfl2k5_player_portrait_fixture/v1",
        "algorithm": "integer neon/checker diagnostic RGBA; deterministic PNG encoder",
        "retail_artwork_included": False,
        "fixture": {"portrait_id": "0124", "file_name": name,
                    "path": str(directory / name), "width": 128, "height": 128,
                    "rgba_sha256": digest(rgba), "png_sha256": digest(png),
                    "png_size": len(png), "non_retail": True},
        "plan_file": "plan.json",
    }
    exclusive(directory / "plan.json",
              json.dumps(plan, indent=2, sort_keys=True).encode() + b"\n")
    exclusive(directory / "fixtures.json",
              json.dumps(report, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"fixtures": 1, "output": str(directory)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
