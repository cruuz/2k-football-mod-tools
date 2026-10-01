#!/usr/bin/env python3
"""DESIGN: compact a read-only Xbox image to a new path and verify every file."""
from pathlib import Path
import argparse
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mod_editor.core.xdvdfs_compact import compact_copy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--order-from", type=Path, help="Read file order from an original image; NFL 2K5 defaults to retail order")
    parser.add_argument("--report", type=Path, help="New JSON report path")
    args = parser.parse_args(argv)
    if args.report is not None and (args.report.exists() or args.report.resolve() in
                                   {args.source.resolve(), args.output.resolve()}):
        parser.error("report must be a separate new path")
    last = 0.0

    def progress(stage, done, total):
        nonlocal last
        now = time.monotonic()
        if now - last >= 10:
            print(f"DESIGN: {stage}: {done:,}/{total:,}", file=sys.stderr, flush=True)
            last = now

    result = compact_copy(args.source, args.output, reference=args.order_from, progress=progress)
    text = json.dumps(result, indent=2) + "\n"
    if args.report is not None:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
