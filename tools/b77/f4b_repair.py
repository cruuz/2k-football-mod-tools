#!/usr/bin/env python3
"""Native v0.5 repair for job F4b: letter grade on the progression screen's overall row (default.xbe only).

Applies on top of the F4-repaired executable (``tools/b77/f4_repair.py``). Input and output are extracted ``default.xbe``
files, never a disc. The repair is a function of the bytes the owner module
``mod_editor/core/nfl2k5_letter_grades_progress.py`` owns, so it composes with every other job's ``default.xbe`` edit
(guards are pinned site bytes, not whole-file hashes). It accepts

* the F4-repaired v0.5 executable (F4 must be applied: the stub points at F4's ``%R`` literal),
* its own deterministic result (idempotent: the output is the input), or
* a stacked integration input that already carries F4, named with ``--expected-input-sha256``.

What it changes (everything else is proved identical, byte for byte):

* 16 owned RX bytes appended as a late owner after F4's (``nfl2k5_xbe_space.extend_scaleout``: every existing allocation is
  proved unmoved): a 15 byte stub that returns the format literal for a progression row;
* 2 pinned 5 byte sites in the progression text callback (``mov edx, 0xEB92F0`` at 0x365E84 and 0x365ED8 become ``call stub``);
* the derived metadata those writes require: the allocator directory page (request document and SHA-256 seals), its header
  copy and the SHA-1 section digests (shared with F4 and the other jobs; whoever applies last recomputes them).

Nothing is written next to the inputs; outputs and the receipt are created exclusively.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_letter_grades as lg  # noqa: E402
from mod_editor.core import nfl2k5_letter_grades_progress as progress  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

V05_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
F4_V05_SHA256 = "78b99479d7c52b6b3f9e380b9734b3a801fae4b8f83a341449959ba4fdb8579b"   # v0.5 after tools/b77/f4_repair.py: the input
FIXED_V05_SHA256 = "d17283fce1248fb6d20d3ecccd139dd1346e01d96437d5d1dfc24cd2ccef4272"   # the deterministic result on the F4-repaired v0.5 executable
MAX_XBE = 16 * 1024 * 1024


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def declared_scopes(before: bytes, after: bytes) -> list[tuple[int, int, str]]:
    """Every file span the repair may touch, from the owner's own layout (computed on the output)."""

    found = progress.allocation(after)
    scopes = [(found["raw"], found["raw"] + progress.CODE_SIZE, "owned RX code (16 bytes)"),
              (space.SCALE_DIRECTORY, space.SCALE_DIRECTORY + space.PAGE, "allocator directory page (requests and SHA-256 seals)"),
              (space.DIRECTORY, space.LIB_COPY, "allocator header copy of the directory seal")]
    for label, va, retail, _patched in progress.sites(found["va"]):
        off = rdata.offset_of(after, va)
        scopes.append((off, off + len(retail), f"site {label} @ {va:#x}"))
    for section in XbeImage(after).sections:
        scopes.append((section.header + 36, section.header + 56, f"{section.name} section SHA-1"))
    scopes.sort()
    for (a, b, _), (c, d, _) in zip(scopes, scopes[1:]):
        if c < b:
            raise ValueError(f"overlapping repair scopes {a:#x}..{b:#x} / {c:#x}..{d:#x}")
    return scopes


def scope_receipt(before: bytes, after: bytes) -> dict:
    if len(before) != len(after):
        raise ValueError("the repair changed the file size")
    scopes = declared_scopes(before, after)
    restored = bytearray(after)
    for start, end, _label in scopes:
        restored[start:end] = before[start:end]
    if bytes(restored) != before:
        stray = [i for i in range(len(before)) if restored[i] != before[i]][:8]
        raise ValueError(f"bytes changed outside the declared scope, first at {[hex(i) for i in stray]}")
    rows = []
    for start, end, label in scopes:
        b, a = before[start:end], after[start:end]
        rows.append({"label": label, "file_offset": hex(start), "size": end - start, "changed": b != a,
                     "before_sha256": sha(b), "after_sha256": sha(a),
                     **({"before_hex": b.hex(), "after_hex": a.hex()} if end - start <= 64 and b != a else {})})
    changed = sum(x != y for x, y in zip(before, after))
    return {"before_sha256": sha(before), "after_sha256": sha(after), "size": len(after), "changed_bytes": changed,
            "scopes": rows, "scopes_total": len(rows), "scopes_changed": sum(r["changed"] for r in rows),
            "outside_scope_identical": True, "outside_scope_restored_sha256": sha(bytes(restored))}


def repair_xbe(payload: bytes) -> tuple[bytes, dict]:
    if lg.status(payload) != "applied":
        raise ValueError("the F4 letter grades repair (tools/b77/f4_repair.py) must be applied first")
    after, apply_receipt = progress.apply(payload)
    receipt = scope_receipt(payload, after)
    old_requests = space._read_scale_directory(payload)
    new_requests = space._read_scale_directory(after)
    old_allocations = space._scale_allocations(old_requests)
    new_allocations = space._scale_allocations(new_requests)
    receipt.update(
        schema="b77.f4b.xbe-repair.v1", disc_file="default.xbe",
        status="already_applied" if after == payload else "applied",
        owner=progress.OWNER,
        added_requests=[list(r) for r in new_requests if r not in old_requests],
        existing_allocations_unchanged=all(row in new_allocations for row in old_allocations),
        owner_allocations=[row for row in new_allocations if row["owner"] == progress.OWNER],
        sites=apply_receipt.get("sites", []), gameplay_witness=False)
    if not receipt["existing_allocations_unchanged"]:
        raise ValueError("an existing allocator owner moved")
    return after, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-input-sha256", help="required for a stacked integration input")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("source must be a regular non-symlink XBE")
    for path in (args.output, args.receipt):
        if path.exists() or path.is_symlink():
            parser.error(f"{path} exists; choose new output and receipt paths")
    if args.output.absolute() == args.receipt.absolute() or args.output.absolute() == args.source.absolute():
        parser.error("source, output and receipt must differ")
    payload = args.source.read_bytes()
    if len(payload) > MAX_XBE:
        parser.error("not an XBE")
    accepted = {args.expected_input_sha256} if args.expected_input_sha256 else {F4_V05_SHA256, FIXED_V05_SHA256}
    if sha(payload) not in accepted:
        parser.error(f"unexpected input SHA-256 {sha(payload)}; no files written")
    result, receipt = repair_xbe(payload)
    receipt.update(source=str(args.source.absolute()), output=str(args.output.absolute()))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(args.output, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(result)
    if sha(args.output.read_bytes()) != receipt["after_sha256"]:
        raise SystemExit("write verification failed")
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("status", "before_sha256", "after_sha256", "changed_bytes",
                                              "scopes_changed", "scopes_total")}))


if __name__ == "__main__":
    main()
