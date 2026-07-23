#!/usr/bin/env python3
"""Create deterministic RGBA PNG fixtures for the NFL scorebug writer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from nfl_txtr import encode_rgba_png
import nfl_tset_png_import as palette_tools


SCHEMA = "nfl2k5_scorebug_fixture/v1"
FIXTURES = (
    ("score_buga", 64, 64, (255, 0, 255, 255)),
    ("shield_espn", 128, 64, (0, 255, 255, 255)),
    ("digital_font", 128, 128, (255, 255, 0, 255)),
)


class FixtureError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FixtureError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def create_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0), 0o644)
    success = False
    try:
        position = 0
        while position < len(payload):
            amount = os.write(descriptor, payload[position:])
            require(amount > 0, "short fixture write")
            position += amount
        os.fsync(descriptor)
        success = True
    finally:
        os.close(descriptor)
        if not success:
            path.unlink(missing_ok=True)


def run(output_dir: Path) -> dict[str, object]:
    parent = output_dir.parent.resolve(strict=True)
    target = parent / output_dir.name
    require(not target.exists() and not target.is_symlink(),
            "output directory already exists")
    os.mkdir(target, 0o755)
    success = False
    try:
        rows = []
        for name, width, height, color in FIXTURES:
            rgba = bytes(color) * (width * height)
            png = encode_rgba_png(width, height, rgba)
            require(palette_tools.decode_rgba_png(png, (width, height)) ==
                    (width, height, rgba), f"{name} fixture strict reparse failed")
            file_name = f"{name}_diagnostic.png"
            create_file(target / file_name, png)
            rows.append({"target": name, "file_name": file_name,
                         "width": width, "height": height,
                         "rgba": list(color), "rgba_sha256": digest(rgba),
                         "png_sha256": digest(png), "png_size": len(png)})
        report: dict[str, object] = {
            "schema": SCHEMA, "fixtures": rows,
            "claims": {"diagnostic_only": True, "originals_modified": False,
                       "xiso_created": False, "runtime_visibility_proved": False},
        }
        create_file(target / "manifest.json", canonical_json(report))
        success = True
        return report
    finally:
        if not success:
            for child in target.iterdir():
                child.unlink()
            target.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.output_dir)
        print("NFL_SCOREBUG_FIXTURE_OK "
              f"count={len(report['fixtures'])} runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
