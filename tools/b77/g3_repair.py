#!/usr/bin/env python3
"""Upgrade the v0.6/v0.6.1 abilities owner: universal retail sprint, star extras.

Apply v1h, v1c, v1i first, then g3 with the exact stacked input SHA-256.
All seals (including .text SHA-1) are derived from the actual output, never
copied from a standalone repair. Input/disc and different outputs are untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

V06_SHA256 = "f67e6fc1cb76c9ea1f1ad504e4a6491ff126483d66a9da8ddb92950bbaf740ba"
SIZE = 12300288
OWNER_RAW, OWNER_VA = 0xB8A000, 0x14DA000
# Exclusive ends. Hook destinations, command tables, tier grants and the
# v1i byte at 0x106D6E are outside this repair's code ranges.
SCOPE = (
    (0x394, 0x3A8, ".text SHA-1 (recomputed, normally unchanged)"),
    (0x90C, 0x920, ".AS0003 SHA-1"),
    (0x97C, 0x990, ".AS0005 SHA-1"),
    (0xDB4, 0xDD4, "allocator directory SHA-256"),
    (OWNER_RAW + 309, OWNER_RAW + 383, "star charge policy"),
    (OWNER_RAW + 450, OWNER_RAW + 528, "ordinary speed ceiling and star extension"),
    (OWNER_RAW + 808, OWNER_RAW + 815, "validate charge before direct consumption"),
    (0xBB600C, 0xBB602C, "allocator RX SHA-256"),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _legacy(payload, settings):
    """Canonicalize only our owner delta plus derived seals for exact replay."""
    buf = bytearray(payload)
    code, _ = abilities.code_for(OWNER_VA, **settings, _legacy_g2=True)
    buf[OWNER_RAW:OWNER_RAW + len(code)] = code
    space._seal_scaleout(buf, space._read_scale_directory(payload))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


def repair_xbe(source: bytes, *, approved=()) -> tuple[bytes, dict]:
    require(len(source) == SIZE, "unexpected default.xbe size")
    require(all(isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) for h in approved),
            "approved input hashes must be lowercase SHA-256")
    state, settings, revision = abilities._inspect_revision(source)
    require(state == "applied" and revision in ("star-gate", "universal-sprint"),
            "expected the exact g2 or g3 abilities owner")
    a = abilities.allocation(source)
    require((a["raw"], a["va"], a["size"]) == (OWNER_RAW, OWNER_VA, 1344),
            "unexpected abilities allocation")
    baseline = _legacy(source, settings) if revision == "universal-sprint" else source
    require(sha(source) in {V06_SHA256, *approved} or sha(baseline) in {V06_SHA256, *approved},
            f"unexpected input SHA-256 {sha(source)}; approve the exact stacked input hash")
    fixed, _ = abilities.repair_sprint(source)
    require(len(fixed) == len(source), "executable size changed")
    changes = [i for i, (a, b) in enumerate(zip(source, fixed)) if a != b]
    require(all(any(lo <= i < hi for lo, hi, _ in SCOPE) for i in changes),
            "change outside declared scope")
    require(abilities.repair_sprint(fixed)[0] == fixed, "repair is not idempotent")
    require(space.status(fixed) == "applied", "allocator/section digest postcondition failed")
    return fixed, {
        "schema": "b77/g3_native_repair/v1", "file": "default.xbe",
        "status": "repaired" if changes else "already_repaired",
        "before_sha256": sha(source), "after_sha256": sha(fixed), "size": SIZE,
        "input_revision": revision, "output_revision": abilities.revision(fixed),
        "settings": settings, "changed_bytes": len(changes),
        "changed_offsets": [hex(i) for i in changes],
        "scope": [{"start": hex(lo), "end_exclusive": hex(hi), "purpose": why,
                   "before_sha256": sha(source[lo:hi]), "after_sha256": sha(fixed[lo:hi])}
                  for lo, hi, why in SCOPE],
        "outside_scope_identical": True, "idempotent": True,
        "hooks_unchanged": True, "tier_grants_unchanged": True,
        "runtime_witnessed": False, "data_files_changed": [],
    }


def read_bounded(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        return stream.read(SIZE + 1)


def write_new(path, data):
    if path.exists():
        require(read_bounded(path) == data, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xbe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--approved-input-sha256", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        require(args.xbe.resolve() != args.output.resolve(), "input and output must differ")
        require(args.receipt.resolve() not in (args.xbe.resolve(), args.output.resolve()), "receipt path overlaps data")
        fixed, receipt = repair_xbe(read_bounded(args.xbe), approved=args.approved_input_sha256)
        report = (json.dumps(receipt, indent=2) + "\n").encode()
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
