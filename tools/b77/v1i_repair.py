#!/usr/bin/env python3
"""Repair v0.6 annual-award timing, preserving v1c/v1h and all other bytes.

Only default.xbe changes: file 0x106D6E (one comparison immediate) and
0x394..0x3A8 (the .text SHA-1). No allocator, runtime code or roster changes.
The disc, input file and existing different outputs are never overwritten.
Stacked inputs require their exact hash via --approved-input-sha256.
For a clean current-season correction, install before Week 17 is completed.
This executable repair does not migrate honors already granted in a save.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_honors as honors
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_xbe_space as space

V06_SHA256 = "f67e6fc1cb76c9ea1f1ad504e4a6491ff126483d66a9da8ddb92950bbaf740ba"
SIZE = 12300288
SCOPE = ((0x394, 0x3A8, ".text SHA-1"), (0x106D6E, 0x106D6F, "annual-awards final week"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def repair_xbe(source: bytes, *, approved=()) -> tuple[bytes, dict]:
    require(len(source) == SIZE, "unexpected default.xbe size")
    require(space.status(source) == "applied", "invalid allocator or section digest")
    require(honors.status(source) == "applied", "F5 code, hooks or dependencies are foreign")
    require(season.group_status(source, "season_length") == "applied", "expected the complete 18-week season")
    before_hash = sha(source)
    # Canonicalizing only our byte and its digest permits exact idempotent
    # replay, without accepting arbitrary files just because the byte is 17.
    old = source
    if source[0x106D6E] == 17:
        old, _ = rdata.apply(source, [("annual_awards", season.AWARDS_WEEK_VA, b"\x11", b"\x10")], "v1i baseline")
    require(before_hash in {V06_SHA256, *approved} or sha(old) in {V06_SHA256, *approved},
            f"unexpected input SHA-256 {before_hash}; approve the exact stacked input hash")
    fixed, timing = season.repair_awards_timing(source)
    require(len(fixed) == len(source), "executable size changed")
    changes = [i for i, (a, b) in enumerate(zip(source, fixed)) if a != b]
    require(all(any(lo <= i < hi for lo, hi, _ in SCOPE) for i in changes), "change outside declared scope")
    require(honors.status(fixed) == "applied" and space.status(fixed) == "applied", "repair postcondition failed")
    require(season.repair_awards_timing(fixed)[0] == fixed, "repair is not idempotent")
    receipt = {
        "schema": "b77/v1i_native_repair/v1", "file": "default.xbe",
        "status": "repaired" if changes else "already_repaired",
        "before_sha256": before_hash, "after_sha256": sha(fixed), "size": SIZE,
        "changed_bytes": len(changes), "changed_offsets": [hex(i) for i in changes],
        "scope": [{"start": hex(lo), "end_exclusive": hex(hi), "purpose": purpose,
                   "before_sha256": sha(source[lo:hi]), "after_sha256": sha(fixed[lo:hi])}
                  for lo, hi, purpose in SCOPE],
        "outside_scope_identical": True, "idempotent": True,
        "honors": honors.status(fixed), "allocator": space.status(fixed), "timing": timing,
        "data_files_changed": [],
    }
    return fixed, receipt


def read_bounded(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        return stream.read(SIZE + 1)


def write_new(path: Path, data: bytes):
    if path.exists():
        require(read_bounded(path) == data, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--approved-input-sha256", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        require(args.xbe.resolve() != args.output.resolve(), "input and output must differ")
        require(args.receipt.resolve() not in (args.xbe.resolve(), args.output.resolve()), "receipt path overlaps data")
        fixed, receipt = repair_xbe(read_bounded(args.xbe), approved=args.approved_input_sha256)
        report = (json.dumps(receipt, indent=2) + "\n").encode("utf-8")
        # Validate both destinations before creating either one.
        for path, data in ((args.output, fixed), (args.receipt, report)):
            require(not path.exists() or read_bounded(path) == data, f"refusing to overwrite {path}")
        write_new(args.output, fixed)
        write_new(args.receipt, report)
        print(json.dumps({k: receipt[k] for k in ("status", "after_sha256", "changed_bytes")}))
        return 0
    except (ValueError, OSError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
