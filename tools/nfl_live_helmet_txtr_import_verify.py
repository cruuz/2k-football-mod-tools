#!/usr/bin/env python3
"""Independently reproduce and verify one live-helmet PNG import directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from nfl_live_helmet_txtr_png_import import (DEFAULT_INDEX, build_import,
                                              canonical_json)
from nfl_live_helmet_txtr_targets import DEFAULT_REPORT


SCHEMA = "nfl2k5_live_helmet_txtr_import_verify/v1"


class VerificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_regular(path: Path, expected_size: int | None, label: str) -> bytes:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        require((info.st_dev, info.st_ino) == (supplied.st_dev, supplied.st_ino) and
                (expected_size is None or info.st_size == expected_size),
                f"{label} pathname/size changed")
        payload = bytearray()
        while len(payload) < info.st_size:
            block = os.read(descriptor, min(1024 * 1024, info.st_size - len(payload)))
            require(bool(block), f"short {label} read")
            payload.extend(block)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (info.st_dev, info.st_ino, info.st_size), f"{label} changed")
        return bytes(payload)
    finally:
        os.close(descriptor)


def verify(index: Path, compatibility: Path, asset_code: str, side: str,
           variant: int, family: str, png: Path, output_dir: Path) -> dict[str, object]:
    expected_span, expected_previews, expected_manifest = build_import(
        index, compatibility, asset_code, side, variant, family, png)
    supplied = output_dir.lstat()
    require(stat.S_ISDIR(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "import output must be a non-symlink directory")
    root = output_dir.resolve(strict=True)
    preview_dir = root / "previews"
    preview_info = preview_dir.lstat()
    require(stat.S_ISDIR(preview_info.st_mode) and
            not stat.S_ISLNK(preview_info.st_mode),
            "preview output must be a non-symlink directory")
    require({item.name for item in root.iterdir()} ==
            {"replacement.txtr.bin", "import.json", "previews"},
            "import output contains missing or extra top-level entries")
    expected_preview_names = {name for name, _ in expected_previews}
    require({item.name for item in preview_dir.iterdir()} == expected_preview_names,
            "preview output contains missing or extra entries")
    actual_span = read_regular(
        root / "replacement.txtr.bin", len(expected_span), "replacement span")
    actual_manifest = read_regular(root / "import.json", None, "import manifest")
    require(actual_span == expected_span and
            actual_manifest == canonical_json(expected_manifest),
            "replacement or canonical import manifest differs from reconstruction")
    preview_hashes: dict[str, str] = {}
    for name, expected in expected_previews:
        actual = read_regular(preview_dir / name, len(expected), f"preview {name}")
        require(actual == expected, f"preview {name} differs from reconstruction")
        preview_hashes[name] = digest(actual)
    manifest_value = json.loads(actual_manifest)
    require(manifest_value.get("schema") ==
            "nfl2k5_live_helmet_txtr_png_import/v1" and
            manifest_value["claims"]["runtime_visibility_proved"] is False and
            manifest_value["claims"]["xemu_started"] is False and
            manifest_value["claims"]["title_executed"] is False and
            manifest_value["claims"]["originals_modified"] is False,
            "import claims changed")
    return {
        "schema": SCHEMA,
        "target": f"{asset_code}{side.upper()}{variant}:{family}",
        "replacement_span_sha256": digest(actual_span),
        "replacement_span_size": len(actual_span),
        "manifest_sha256": digest(actual_manifest),
        "preview_sha256": preview_hashes,
        "previews_verified": len(preview_hashes),
        "reconstructed_exactly": True,
        "originals_modified": False,
        "runtime_visibility_proved": False,
        "xemu_started": False,
        "title_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-code", required=True)
    parser.add_argument("--target-side", required=True)
    parser.add_argument("--target-variant", type=int, required=True)
    parser.add_argument("--family", choices=("helmet00", "helmet02"), required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(
            args.index, args.compatibility, args.target_code, args.target_side,
            args.target_variant, args.family, args.png, args.output_dir)
        print(
            "NFL_LIVE_HELMET_TXTR_IMPORT_VERIFY_PASS "
            f"target={result['target']} span={result['replacement_span_sha256']} "
            f"previews={result['previews_verified']} runtime=false xemu_started=false"
        )
        return 0
    except (VerificationError, OSError, ValueError, KeyError,
            json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
