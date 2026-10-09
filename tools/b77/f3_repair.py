#!/usr/bin/env python3
"""Scoped v0.5 XBE repair (job F3): the franchise Player Card TEAM column follows trades, signings and releases.

Input and output are extracted ``default.xbe`` files, never a disc.  The CLI accepts the exact v0.5 executable
(or its repaired result, which is idempotent).  Integration on a file that other repairs already changed needs the
explicit whole-file SHA-256 of that composed input; the native owner guard (``nfl2k5_team_column.revision``) must
still read the TEAM column as the revision-1 layout (1) or as already revision 2.

What is owned (all three are inside the TEAM-column patch's own ranges and nothing else is written):

* ``cave``      VA 0x47220..0x47420 (file 0x37220..0x37420, 512 bytes): the revision-2 caves, strings and the
                column descriptor (its getter pointer moves);
* ``post_hook`` VA 0x134E0A (file 0x124E0A, 7 bytes): ``mov ecx,ebx ; call 0x61b90`` -> ``jmp post ; nop ; nop``;
* ``text_digest`` the 20-byte ``.text`` section digest in the section header (derived, recomputed).

The rollover hook at 0x247C1B and the six Player Card column lists already carry the exact revision-1 bytes (they
are verified identical, not rewritten).  No output overwrites an input; every byte outside the three scopes is
proved identical in the receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_team_column as tc
from mod_editor.core.nfl2k5_bump_strength import _sections

SCHEMA = "b77.f3.team-column-repair.v1"
V05_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
V05_REPAIRED_SHA256 = "94328ab8e6d9f4ffd724d68bc8f88ff28e6528a956cfe5d17990bf56485d98ab"
MAX_XBE = 16 * 1024 * 1024


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def declared_scopes(payload: bytes) -> list[dict]:
    """The exact byte ranges this repair may change, as file offsets of ``payload``."""

    text = [s for s in _sections(payload) if s.index == 0][0]
    return [
        {"name": "cave", "va": tc.CAVE_VA, "file_offset": tc._offset(payload, tc.CAVE_VA), "size": tc.CAVE_SIZE},
        {"name": "post_hook", "va": tc.POST_HOOK_VA, "file_offset": tc._offset(payload, tc.POST_HOOK_VA),
         "size": tc.POST_HOOK_SIZE},
        {"name": "text_section_digest", "va": None, "file_offset": text.header_offset + 36, "size": 20},
    ]


def changed_runs(before: bytes, after: bytes) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, (a, b) in enumerate(zip(before, after)):
        if a != b and start is None:
            start = i
        elif a == b and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(before)))
    return runs


def prove_scope(before: bytes, after: bytes, scopes: list[dict]) -> dict:
    if len(before) != len(after):
        raise ValueError("the repair changed the file size")
    covered = bytearray(len(before))
    for scope in scopes:
        covered[scope["file_offset"]: scope["file_offset"] + scope["size"]] = b"\x01" * scope["size"]
    stray = []
    for run_start, run_end in changed_runs(before, after):
        if any(not covered[i] for i in range(run_start, run_end)):
            stray.append((run_start, run_end))
    # hash everything outside the scopes (in file order) on both sides
    h_before, h_after = hashlib.sha256(), hashlib.sha256()
    cursor = 0
    for scope in sorted(scopes, key=lambda s: s["file_offset"]):
        h_before.update(before[cursor: scope["file_offset"]])
        h_after.update(after[cursor: scope["file_offset"]])
        cursor = scope["file_offset"] + scope["size"]
    h_before.update(before[cursor:])
    h_after.update(after[cursor:])
    return {"outside_scope_identical": not stray and h_before.hexdigest() == h_after.hexdigest(),
            "outside_scope_sha256": h_after.hexdigest(), "outside_scope_sha256_before": h_before.hexdigest(),
            "stray_runs": [f"0x{a:x}..0x{b:x}" for a, b in stray]}


def repair_xbe(payload: bytes) -> tuple[bytes, dict]:
    before_revision = tc.revision(payload)
    if before_revision not in (1, 2):
        raise ValueError(f"TEAM-column sites are {tc.status(payload)}, expected the revision-1 layout or revision 2")
    result, component = tc.apply(payload)
    scopes = declared_scopes(payload)
    proof = prove_scope(payload, result, scopes)
    if not proof["outside_scope_identical"]:
        raise ValueError(f"the repair changed bytes outside its scopes: {proof['stray_runs']}")
    receipt_scopes = []
    for scope in scopes:
        a, b = scope["file_offset"], scope["file_offset"] + scope["size"]
        receipt_scopes.append({"name": scope["name"], "va": None if scope["va"] is None else f"0x{scope['va']:x}",
                               "file_offset": f"0x{a:x}", "size": scope["size"],
                               "before_sha256": sha(payload[a:b]), "after_sha256": sha(result[a:b]),
                               "bytes_changed": sum(1 for x, y in zip(payload[a:b], result[a:b]) if x != y)})
    verified_identical = [{"name": "rollover_hook", "va": f"0x{tc.HOOK_VA:x}", "size": tc.HOOK_SIZE}]
    verified_identical += [{"name": f"list_{label}", "va": f"0x{va + tc.LIST_POINTERS_OFF:x}", "size": tc.LIST_SLOTS * 4}
                           for label, va, _pointers in tc.COLUMN_LISTS]
    for item in verified_identical:
        off = tc._offset(payload, int(item["va"], 16))
        if payload[off: off + item["size"]] != result[off: off + item["size"]]:
            raise ValueError(f"{item['name']} changed")
    return result, dict(
        schema=SCHEMA, disc_file="default.xbe", before_sha256=sha(payload), after_sha256=sha(result), size=len(result),
        status="already_applied" if before_revision == 2 else "applied",
        upgraded_from_revision=None if before_revision == 2 else before_revision,
        changed_bytes=sum(1 for a, b in zip(payload, result) if a != b),
        changed_runs=[f"0x{a:x}..0x{b:x}" for a, b in changed_runs(payload, result)],
        scopes=receipt_scopes, verified_identical_not_rewritten=verified_identical,
        outside_scope_identical=True, outside_scope_sha256=proof["outside_scope_sha256"],
        revision=2, component={k: v for k, v in component.items() if k != "edits"},
        gameplay_witness=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-input-sha256")
    args = parser.parse_args()
    if args.source.is_symlink() or not args.source.is_file():
        parser.error("Source must be a regular non-symlink XBE")
    for path in (args.output, args.receipt):
        if path.exists() or path.is_symlink():
            parser.error("Output and receipt must be new paths")
    if args.output.absolute() == args.receipt.absolute():
        parser.error("Output and receipt must differ")
    with args.source.open("rb") as stream:
        payload = stream.read(MAX_XBE + 1)
    if len(payload) > MAX_XBE:
        parser.error("Input is larger than 16 MiB")
    accepted = {args.expected_input_sha256} if args.expected_input_sha256 else {V05_SHA256, V05_REPAIRED_SHA256}
    if sha(payload) not in accepted:
        parser.error("Unexpected input SHA256; no files written")
    result, receipt = repair_xbe(payload)
    if not args.expected_input_sha256 and receipt["after_sha256"] != V05_REPAIRED_SHA256:
        raise SystemExit("the repaired v0.5 executable does not match its pinned SHA256; no files written")
    receipt.update(source=str(args.source.absolute()), output=str(args.output.absolute()))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(args.output, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(result)
    with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("status", "before_sha256", "after_sha256", "changed_bytes")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
