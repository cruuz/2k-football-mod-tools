#!/usr/bin/env python3
"""Thin CLI over mod_editor.core.nfl2k5_catch_slider: write a patched COPY (XBE or disc image)
with the Catching-slider cave (see the core module docstring). Prefer the studio panel."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402

def main() -> int:
    if len(sys.argv) < 3:
        print("usage: nfl2k5_catch_slider_patch.py SOURCE TARGET [--overwrite]", file=sys.stderr); return 2
    r = tt.write_copy(sys.argv[1], sys.argv[2], catch_slider=True, overwrite="--overwrite" in sys.argv)
    print("catch_slider:", r["catch_slider"], "| changed bytes:", r.get("changed_byte_count")); return 0

if __name__ == "__main__":
    raise SystemExit(main())
