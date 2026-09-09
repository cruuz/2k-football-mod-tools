#!/usr/bin/env python3
"""Inspect book identity or build offline-verified clones/presets in a new folder."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core.apf2k8_book_clone import (  # noqa: E402
    build_new_folder, compile_unlock, requests_from_json,
)
from mod_editor.core.apf2k8_book_identity import disc_book_identity_report  # noqa: E402
from mod_editor.core.errors import ValidationError  # noqa: E402
from mod_editor.core.apf2k8_scheme_presets import (  # noqa: E402
    PRESET_IDS, build_presets_folder, compile_preset, load_preset,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("identity", "clone", "preset"):
        sub = commands.add_parser(name)
        sub.add_argument("--source", type=Path, required=True, help="User-owned game index, named 0A")
        sub.add_argument("--receipt", type=Path, help="New JSON receipt file (never overwritten)")
        if name != "identity":
            sub.add_argument("--output", type=Path, help="New game directory; omit to compile/review only")
        if name == "clone":
            sub.add_argument("--requests", type=Path, required=True)
        if name == "preset":
            sub.add_argument("--preset", choices=PRESET_IDS, action="append", required=True)
    args = parser.parse_args(argv)
    try:
        if args.receipt and args.receipt.exists():
            raise ValueError("Receipt destination already exists")
        progress = lambda message: print(message, file=sys.stderr, flush=True)
        if args.command == "identity":
            report = disc_book_identity_report(args.source)
        elif args.command == "clone":
            plan = compile_unlock(args.source, requests_from_json(args.requests.read_bytes()))
            report = build_new_folder(plan, args.output, progress) if args.output else plan.report
        else:
            report = (build_presets_folder(args.source, tuple(args.preset), args.output, progress)
                      if args.output else {"presets": [compile_preset(args.source, load_preset(x)).report
                                                     for x in args.preset]})
        text = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.receipt:
            with args.receipt.open("x", encoding="utf-8") as stream:
                stream.write(text)
        else:
            print(text, end="")
        return 0
    except (OSError, ValueError, RuntimeError, ValidationError) as exc:
        print(f"Book operation refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
