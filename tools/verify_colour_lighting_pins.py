#!/usr/bin/env python3
"""Read-only exhaustive v2.1 reproduction; no retail bytes or rebuilt pins are saved."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_modern_color as colour


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    expected = colour._pins()
    actual = colour.build_pins(args.source, workers=args.workers,
                               progress=lambda message, done, total: print(message, flush=True) if done % 50 == 0 else None)
    for family in ('bundles', 'light_tables'):
        assert actual[family] == expected[family], f'{family}: v2.1 byte pins changed'
    print(f"PASS: {len(actual['bundles'])} complete bundle pins and {len(actual['light_tables'])} light tables reproduce v2.1")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
