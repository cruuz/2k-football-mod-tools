#!/usr/bin/env python3
"""EXPERIMENTAL/UNWITNESSED normal kickoff return assignments, fixed PLAY spans."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import nfl2k5_kickoff_alignment as alignment
from mod_editor.core import nfl2k5_kickoff_returns as returns


def status(path):
    with alignment.recode.OuterImage(path) as archive:
        rows = [{"book": book.name, "status": returns.status(archive.read_entry(book.entry_index))}
                for book, _ in alignment._load(archive)]
    states = {r["status"] for r in rows}
    return {"status": next(iter(states)) if len(states) == 1 else "foreign", "books": len(rows), "rows": rows}


def apply(path, *, progress=None):
    progress = progress or (lambda _message: None)
    receipts = []
    with alignment.recode.OuterImage(path, writable=True) as archive:
        # Validate and compile every resource before the first archive write.
        plans = []
        for book, _ in alignment._load(archive):
            raw = archive.read_entry(book.entry_index)
            replacement, receipt = returns.apply(raw)
            plans.append((book, raw, replacement, receipt))
        states = {receipt["status"] for _, _, _, receipt in plans}
        if len(states) != 1:
            raise ValueError("mixed normal return assignments across books")
        for book, raw, replacement, receipt in plans:
            progress(f"{book.name}: local kickoff return blocking")
            for edit in receipt["edits"]:
                offset = book.virtual_offset + edit["offset"]
                before, after = bytes.fromhex(edit["before"]), bytes.fromhex(edit["after"])
                if archive.read(offset, len(before)) != before:
                    raise ValueError(f"{book.name}: source changed before write")
                archive.write(offset, after)
                if archive.read(offset, len(after)) != after:
                    raise ValueError(f"{book.name}: write verification failed")
                edit["virtual_offset"] = offset
            receipts.append({"book": book.name, **receipt})
    return {"status": "applied", "experimental": True, "witnessed": False,
            "books": len(receipts), "changed_bytes": sum(r["changed_bytes"] for r in receipts),
            "receipts": receipts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "apply"))
    parser.add_argument("path", help="extracted archive directory or disposable image copy")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    receipt = status(args.path) if args.command == "status" else apply(args.path)
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k not in ("rows", "receipts")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
