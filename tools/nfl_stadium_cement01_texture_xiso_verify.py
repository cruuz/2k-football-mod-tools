#!/usr/bin/env python3
"""Independently verify a bounded cement01 stadium-texture copied XISO."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.nfl2k5_stadium_texture_verify import (  # noqa: E402
    StadiumTextureVerifyError,
    verify_stadium_texture_xiso,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-xiso", required=True, type=Path)
    parser.add_argument("--output-xiso", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify_stadium_texture_xiso(
            args.source_xiso, args.output_xiso, args.manifest
        )
    except (OSError, StadiumTextureVerifyError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
