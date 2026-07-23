#!/usr/bin/env python3
"""Independently reconstruct and verify one Team Select card import bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any

from nfl_team_select_card_png_import import (SCHEMA, build_import,
                                               canonical_json)
from nfl_team_select_card_targets import DEFAULT_REPORT


class VerifyError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerifyError(message)


def read_regular(path: Path, label: str, expected_size: int | None = None) -> bytes:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be a non-symlink regular file")
    if expected_size is not None:
        require(info.st_size == expected_size, f"{label} size mismatch")
    return path.resolve(strict=True).read_bytes()


def verify(index: Path, compatibility: Path, family: str, asset_code: str,
           side: str, style: int, resolution: int, png: Path,
           replacement: Path, preview: Path, manifest: Path) -> dict[str, Any]:
    manifest_payload = read_regular(manifest, "import manifest")
    try:
        value = json.loads(manifest_payload)
    except json.JSONDecodeError as exc:
        raise VerifyError("import manifest is invalid JSON") from exc
    require(value.get("schema") == SCHEMA and
            manifest_payload == canonical_json(value),
            "import manifest schema/canonical encoding mismatch")
    names = {
        "span_file": replacement.name,
        "manifest_file": manifest.name,
        "preview_file": preview.name,
    }
    expected_span, expected_preview, expected_value = build_import(
        index, compatibility, family, asset_code, side, style, resolution,
        png, names)
    replacement_payload = read_regular(
        replacement, "replacement span", len(expected_span))
    preview_payload = read_regular(preview, "preview", len(expected_preview))
    require(manifest_payload == canonical_json(expected_value) and
            replacement_payload == expected_span and
            preview_payload == expected_preview,
            "import bundle differs from independent reconstruction")
    require(value["replacement"]["span_sha256"] ==
            hashlib.sha256(replacement_payload).hexdigest() and
            value["preview"]["sha256"] == hashlib.sha256(preview_payload).hexdigest() and
            value["claims"]["runtime_visibility_proved"] is False,
            "import bundle hashes/claims mismatch")
    return {
        "selector": value["target"]["selector"],
        "replacement_sha256": value["replacement"]["span_sha256"],
        "preview_sha256": value["preview"]["sha256"],
        "changed_bytes": value["replacement"]["changed_byte_count"],
        "independently_reconstructed": True,
        "runtime_visibility_proved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path,
                        default=Path("extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"))
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--family", required=True)
    parser.add_argument("--asset-code", required=True)
    parser.add_argument("--side", required=True)
    parser.add_argument("--style", required=True, type=int)
    parser.add_argument("--resolution", required=True, type=int)
    parser.add_argument("--png", required=True, type=Path)
    parser.add_argument("--replacement", required=True, type=Path)
    parser.add_argument("--preview", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(
            args.index, args.compatibility, args.family, args.asset_code,
            args.side, args.style, args.resolution, args.png,
            args.replacement, args.preview, args.manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
