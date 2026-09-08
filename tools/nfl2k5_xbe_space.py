#!/usr/bin/env python3
"""Offline owned-space capacity planner. Requests never build or write a disc."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_xbe_space as space


def read_requests(path):
    if path.stat().st_size > 32768:
        raise ValueError("request JSON exceeds 32768 bytes")
    document = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(document, dict):
        if set(document) != {"requests"}:
            raise ValueError("request object must contain only requests")
        document = document["requests"]
    if not isinstance(document, list):
        raise ValueError("requests must be a JSON array of [owner, kind, size, align]")
    return document


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan", help="refuse over-budget requests before a build")
    planner.add_argument("--requests", type=Path, required=True)
    planner.add_argument("--json", action="store_true", help="print the complete machine-readable page map")
    args = parser.parse_args(argv)
    try:
        report = space.plan(read_requests(args.requests))
    except (OSError, ValueError, TypeError) as exc:
        print(f"XBE space plan refused: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("EXPERIMENTAL / UNWITNESSED: owned XBE space, beta 62")
        print("Realize this v3 map with apply(payload, requests, scaleout=True).")
        print("Kind       Page  VA          Raw         Free bytes  Children")
        for page in report["pages"]:
            owners = ", ".join(child["owner"] for child in page["children"]) or "reserved padding"
            print(f"{page['kind']:10} {page['page']:4}  {page['va']:#010x}  {page['raw']:#010x}  {page['free_bytes']:10}  {owners}")
        for kind, row in report["capacity"].items():
            print(f"{kind}: {row['capacity_bytes']} bytes in {row['pages']} pages; "
                  f"{row['free_bytes']} free; {row['available_bytes']} available to new owners before alignment")
        print(f"PASS: {len(report['requests'])} requests; XBE size {report['file_size']} bytes. No build performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
