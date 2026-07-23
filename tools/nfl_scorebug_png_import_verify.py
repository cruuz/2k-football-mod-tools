#!/usr/bin/env python3
"""Reconstruct and verify one NFL 2K5 scorebug PNG import directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from nfl_scorebug_png_import import (DEFAULT_AUDIT, DEFAULT_INDEX, TARGET_NAMES,
                                      build_import, canonical_json)


class VerificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_regular(path: Path, label: str, maximum: int) -> bytes:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            f"{label} must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                         getattr(os, "O_CLOEXEC", 0))
    try:
        info = os.fstat(descriptor)
        require(info.st_size <= maximum and
                (info.st_dev, info.st_ino) == (supplied.st_dev, supplied.st_ino),
                f"{label} identity/size changed")
        result = bytearray()
        while len(result) < info.st_size:
            block = os.read(descriptor, min(1024 * 1024, info.st_size - len(result)))
            require(bool(block), f"short {label} read")
            result.extend(block)
        require(not os.read(descriptor, 1), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (info.st_dev, info.st_ino, info.st_size), f"{label} changed")
        return bytes(result)
    finally:
        os.close(descriptor)


def verify(index: Path, audit: Path, target: str, png: Path,
           output_dir: Path) -> dict[str, object]:
    supplied = output_dir.lstat()
    require(stat.S_ISDIR(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "output directory must be a non-symlink directory")
    root = output_dir.resolve(strict=True)
    current = root.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino) == (supplied.st_dev, supplied.st_ino),
            "output directory identity changed")
    require({path.name for path in root.iterdir()} ==
            {"replacement.txtr.bin", "preview.png", "import.json"},
            "output directory has missing or extra files")
    expected_span, expected_preview, expected_report = build_import(
        index, audit, target, png)
    actual_span = read_regular(root / "replacement.txtr.bin", "replacement span",
                               32 * 1024 * 1024)
    actual_preview = read_regular(root / "preview.png", "preview PNG",
                                  32 * 1024 * 1024)
    actual_manifest = read_regular(root / "import.json", "import manifest",
                                   64 * 1024 * 1024)
    require(actual_span == expected_span and actual_preview == expected_preview and
            actual_manifest == canonical_json(expected_report),
            "import output differs from independent reconstruction")
    parsed = json.loads(actual_manifest)
    claims = parsed["claims"]
    require(claims["fixed_span_only"] is True and
            claims["originals_modified"] is False and
            claims["xiso_created"] is False and claims["xemu_started"] is False and
            claims["title_executed"] is False and
            claims["runtime_visibility_proved"] is False,
            "import safety claims changed")
    return {
        "target": target, "span_size": len(actual_span),
        "span_sha256": digest(actual_span),
        "preview_sha256": digest(actual_preview),
        "changed_bytes": parsed["rebuild"]["changed_byte_count"],
        "runtime_visibility_proved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--target", choices=TARGET_NAMES, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.index, args.audit, args.target, args.png, args.output_dir)
        print("NFL_SCOREBUG_PNG_IMPORT_VERIFY_PASS "
              f"target={result['target']} changed={result['changed_bytes']} "
              "runtime=false")
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
