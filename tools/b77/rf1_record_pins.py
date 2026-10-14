#!/usr/bin/env python3
"""rf1: write data/nfl2k5_modern_officials/pins.json from a retail USA image and the shipped officials art (read only).

  python3 tools/b77/rf1_record_pins.py --retail "ESPN NFL 2K5 (USA).xiso.iso"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_officials as mo  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--retail", type=Path, required=True)
    a = ap.parse_args(argv)
    document = mo.record_pins(a.retail)
    mo.PINS_PATH.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8", newline="\n")
    for row in document["parts"]:
        print(f"{row['part']:>14} chunk {row['chunk_index']:3d} span {row['span_size']:7d} palette {row['palette_max']:3d} "
              f"scratch {row['fit']['scratch_needed']}/{row['fit']['scratch_retail']} {row['applied_sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
