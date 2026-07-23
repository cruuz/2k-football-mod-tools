#!/usr/bin/env python3
"""Create deterministic non-retail PNG fixtures for Team Select card tests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from nfl_txtr import encode_rgba_png


SCHEMA = "nfl2k5_team_select_card_fixture/v1"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fixture(kind: str, width: int = 256, height: int = 256) -> bytes:
    result = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            if kind == "unif":
                band = ((x // 16) + 3 * (y // 16)) & 15
                red = (band * 37 + 29) & 255
                green = (band * 71 + 83) & 255
                blue = (band * 19 + 191) & 255
                alpha = (0, 96, 176, 255)[((x // 32) ^ (y // 32)) & 3]
                if 72 <= x < 184 and 48 <= y < 208:
                    red, green, blue, alpha = (255, 0, 203, 255) \
                        if ((x // 12 + y // 12) & 1) else (0, 231, 255, 224)
            elif kind == "helm":
                cell = ((x // 8) ^ (y // 8) ^ ((x + y) // 32)) & 31
                red = (cell * 53 + 17) & 255
                green = (cell * 29 + 211) & 255
                blue = (cell * 97 + 41) & 255
                alpha = (0, 64, 128, 192, 255)[cell % 5]
                dx, dy = x - 128, y - 116
                if dx * dx + dy * dy < 92 * 92:
                    red, green, blue, alpha = (36, 255, 72, 255) \
                        if ((x // 10) & 1) else (108, 20, 255, 255)
            else:
                raise ValueError(kind)
            offset = (y * width + x) * 4
            result[offset:offset + 4] = bytes((red, green, blue, alpha))
    return bytes(result)


def exclusive(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
        getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0), 0o644)
    try:
        position = 0
        while position < len(payload):
            written = os.write(descriptor, payload[position:])
            if written <= 0:
                raise OSError("short fixture write")
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
    names = {
        "unif": "detroit_away_style0_unif_nonretail.png",
        "helm": "detroit_away_style0_helm_nonretail.png",
    }
    records = []
    for family, name in names.items():
        rgba = fixture(family)
        png = encode_rgba_png(256, 256, rgba)
        target = directory / name
        exclusive(target, png)
        records.append({
            "family": family, "asset_code": "09", "side": "away",
            "style": 0, "resolution": 256, "path": str(target),
            "file_name": name, "width": 256, "height": 256,
            "rgba_sha256": digest(rgba), "png_sha256": digest(png),
            "png_size": len(png), "non_retail": True,
        })
    plan_edits = [{
        "family": record["family"],
        "asset_code": record["asset_code"],
        "side": record["side"],
        "style": record["style"],
        "resolution": record["resolution"],
        "png": record["path"],
    } for record in records]
    plan = {
        "schema": "nfl2k5_team_select_card_plan/v1",
        "purpose": "deterministic non-retail dual-card copy-only proof",
        "edits": plan_edits,
    }
    report = {
        "schema": SCHEMA,
        "algorithm": "integer tile/band diagnostic RGBA; deterministic PNG encoder",
        "retail_artwork_included": False,
        "fixtures": records,
        "plan_file": "plan.json",
    }
    exclusive(directory / "plan.json", json.dumps(plan, indent=2, sort_keys=True).encode() + b"\n")
    exclusive(directory / "fixtures.json", json.dumps(report, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"fixtures": len(records), "output": str(directory)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
