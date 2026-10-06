#!/usr/bin/env python3
"""Compose p2's clean fallback with p1; only default.xbe can change.

Modern squads remain unavailable. This retains p1's exact functional ranges
and adds complete Studio owner validation before publishing a repaired copy.
Already repaired p1 inputs are byte-identical. Sibling repairs require an
independently recorded input SHA-256, as with p1.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b765 import p1_repair
from mod_editor.core import nfl2k5_practice_squad_screen as screen


def repair(payload: bytes, *, expected_input_sha256: str | None = None):
    result, receipt = p1_repair.repair(payload, expected_input_sha256=expected_input_sha256)
    # A caller-supplied hash admits sibling work, never altered PS code/tables.
    studio, _ = screen.apply(payload)
    if studio != result:
        raise ValueError('Studio/native fallback differs; refusing to publish')
    return result, dict(receipt, schema='b765-p2-native-repair/v1',
                        composes_with='b765-p1', studio_owner_validated=True,
                        modern_practice_squad=False,
                        outcome='clean removal; existing reserve storage retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-xbe', required=True, type=Path)
    parser.add_argument('--output-xbe', required=True, type=Path)
    parser.add_argument('--receipt', required=True, type=Path)
    parser.add_argument('--expected-input-sha256')
    args = parser.parse_args()
    if len({p.resolve() for p in (args.input_xbe, args.output_xbe, args.receipt)}) != 3:
        parser.error('input, output and receipt must be separate paths')
    try:
        fixed, receipt = repair(args.input_xbe.read_bytes(), expected_input_sha256=args.expected_input_sha256)
        p1_repair.write_copy(args.output_xbe, fixed)
        p1_repair.write_copy(args.receipt, (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
        print(json.dumps(receipt, indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.exit(2, f'p2 repair refused: {exc}\n')


if __name__ == '__main__':
    main()
