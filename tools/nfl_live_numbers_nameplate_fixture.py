#!/usr/bin/env python3
"""Generate deterministic non-retail live-number/nameplate test PNGs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from nfl_txtr import encode_rgba_png
from nfl_tset_png_import import decode_rgba_png


SCHEMA = "nfl2k5_live_numbers_nameplate_fixture/v1"


class FixtureError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def image(width: int, height: int, role: str) -> bytes:
    rgba = bytearray(width * height * 4)
    colors = (
        (0, 0, 0, 0), (255, 0, 192, 255),
        (0, 255, 255, 255), (64, 255, 0, 255),
    )
    for y in range(height):
        for x in range(width):
            if role == "nameplate":
                cell = y // 32
                inside = 3 <= x < 29 and (y % 32) in range(4, 28)
                border = inside and (x in {3, 28} or (y % 32) in {4, 27})
                stripe = inside and ((x + y + cell * 3) % 11 < 3)
                index = 1 + (cell % 3) if (border or stripe) else 0
            else:
                margin = max(2, width // 12)
                inside = margin <= x < width - margin and margin <= y < height - margin
                diagonal = inside and ((x + y) % max(4, width // 8) < max(2, width // 16))
                cross = inside and (abs(x - width // 2) <= 1 or abs(y - height // 2) <= 1)
                index = 2 if cross else 1 if diagonal else 0
            rgba[(y * width + x) * 4:(y * width + x) * 4 + 4] = bytes(colors[index])
    payload = encode_rgba_png(width, height, bytes(rgba))
    require(decode_rgba_png(payload, (width, height)) ==
            (width, height, bytes(rgba)), "fixture PNG strict reparse failed")
    return payload


def write_exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o644)
    try:
        offset = 0
        while offset < len(payload):
            amount = os.write(descriptor, payload[offset:])
            require(amount > 0, "short fixture write")
            offset += amount
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        parent = args.output_dir.parent.resolve(strict=True)
        output = parent / args.output_dir.name
        require(not output.exists(), "output directory already exists")
        os.mkdir(output, 0o755)
        generated = {
            "digit_64": ("detroit_away_style0_digit5_64_nonretail.png", image(64, 64, "digit")),
            "digit_32": ("detroit_away_style0_digit5_32_nonretail.png", image(32, 32, "digit")),
            "nameplate": ("detroit_away_style0_nameplate_nonretail.png", image(32, 1024, "nameplate")),
        }
        rows = []
        for role, (name, payload) in generated.items():
            path = output / name
            write_exclusive(path, payload)
            width, height, rgba = decode_rgba_png(payload, None)
            rows.append({"role": role, "file": name, "width": width, "height": height,
                         "png_sha256": digest(payload), "rgba_sha256": digest(rgba)})
        manifest = {"schema": SCHEMA, "purpose": "programmatic non-retail transport fixture",
                    "contains_retail_art": False, "files": rows}
        payload = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
        write_exclusive(output / "fixture_manifest.json", payload)
        print(f"NFL_LIVE_NUMBERS_NAMEPLATE_FIXTURE_COMPLETE files={len(rows)}")
        return 0
    except (FixtureError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
