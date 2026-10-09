#!/usr/bin/env python3
"""Native H1 repair of the v0.5 disc's default.xbe: the punter holds on field goals and PATs.

Reads one disc file (``default.xbe``), writes a repaired copy and a receipt; no input is modified and no disc image
is opened.  The change is the Studio's ``nfl2k5_punter_holder`` patch, applied to exactly the bytes this job owns:

* ``.text`` VA 0xE8006..0xE800F (file 0xD8006, 9 bytes): inside the depth-chart builder FUN_000e7c50,
  ``mov eax,[ebp] ; mov bl,[eax+0x194]`` becomes ``jmp 0x24B10`` plus four nops,
* ``.text`` VA 0x24B10..0x24B40 (file 0x14B10, 48 bytes): the dead vec4-subtract routine and its nop pad become the
  47-byte cave (int3 fill after it); no reference in the retail or v0.5 image lands on those bytes,
* the SHA-1 digest field of ``.text`` in the XBE header (20 bytes, derived from the whole section, so an integrator
  re-derives it after stacking every owner of that section).

Everything else in the file is identical (checked by a scope receipt).  The file keeps its size.

default.xbe is shared with other b77 jobs.  Stacked input: pass that job's output with
``--expected-xbe-sha256 <its after_sha256>`` (repeatable) or ``--accepted-input-hashes <its receipt.json>``.
An input that already carries the patch is a recorded no-op.  Input whose edited bytes are neither retail nor
patched, or whose pinned context differs, is refused.  EXPERIMENTAL / UNWITNESSED in a played game.
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
from mod_editor.core import nfl2k5_punter_holder as holder
from mod_editor.core.nfl2k5_bump_strength import _section_for_offset, _sections, section_digest

SCHEMA = "b77/h1_native_repair/v1"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
V05_FIXED_XBE_SHA256 = "b9459638720d2ce6b0e39381dfbef8a33f336acb7c472a6b0b73fcae5d7ad3e8"
DISC_FILE = "default.xbe"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read(path: Path) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read()


def write_new(path: Path, raw: bytes) -> None:
    """Create the file, or accept an existing identical one; never replace different bytes."""
    if path.exists():
        if read(path) != raw:
            raise ValueError(f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def scope_receipt(before: bytes, after: bytes, spans: list[tuple[int, int]]) -> dict:
    """Prove every byte outside the declared spans is identical (restore the spans, compare the whole file)."""
    if len(before) != len(after):
        raise ValueError("repair changed the file size")
    restored = bytearray(after)
    for offset, size in spans:
        if offset < 0 or size < 0 or offset + size > len(before):
            raise ValueError("invalid repair scope")
        restored[offset:offset + size] = before[offset:offset + size]
    if bytes(restored) != before:
        raise ValueError("repair changed bytes outside the declared scope")
    changed = sum(1 for a, b in zip(before, after) if a != b)
    return {"before_sha256": sha(before), "after_sha256": sha(after), "size": len(after), "changed_bytes": changed,
            "scope": [{"offset": o, "size": s} for o, s in spans], "outside_scope_identical": True,
            "outside_scope_restored_sha256": sha(bytes(restored))}


def declared_spans(payload: bytes) -> tuple[list[tuple[int, int]], list[dict]]:
    spans, ranges = [], []
    sections = _sections(payload)
    digest_fields = {}
    for label, va, before, after in holder.sites():
        offset = holder._offset(payload, va)
        spans.append((offset, len(before)))
        ranges.append({"label": label, "va": hex(va), "file_offset": hex(offset), "size": len(before),
                       "retail_sha256": sha(before), "patched_sha256": sha(after)})
        section = _section_for_offset(sections, offset)
        digest_fields[section.index] = section
    for index, section in sorted(digest_fields.items()):
        spans.append((section.header_offset + 36, 20))
        ranges.append({"section_index": index, "section_va": hex(section.virtual_address),
                       "header_field_offset": hex(section.header_offset + 36), "size": 20,
                       "basis": "derived: SHA-1 of the whole section; re-derive after stacking owners"})
    return spans, ranges


def accepted_hashes(args) -> set[str]:
    accepted = {V05_XBE_SHA256, *(h.lower() for h in args.expected_xbe_sha256 or [])}
    if args.accepted_input_hashes:
        doc = json.loads(read(args.accepted_input_hashes))
        files = doc.get("files", doc)
        row = files.get(DISC_FILE)
        digest = row if isinstance(row, str) else (row or {}).get("sha256", (row or {}).get("after_sha256"))
        if not isinstance(digest, str):
            raise ValueError("accepted input manifest has no default.xbe hash")
        accepted.add(digest.lower())
    for digest in accepted:
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"invalid accepted SHA-256: {digest}")
    return accepted


def audit_digests(payload: bytes) -> bool:
    return all(payload[s.header_offset + 36:s.header_offset + 56] == section_digest(payload, s) for s in _sections(payload))


def repair(payload: bytes, accepted: set[str]) -> tuple[bytes, dict]:
    digest = sha(payload)
    state = holder.status(payload)
    if state == "foreign":
        raise ValueError("default.xbe is not retail-shaped at the punter-holder hook and cave, or its pinned context differs")
    if digest not in accepted and not (state == "applied" and digest == V05_FIXED_XBE_SHA256):
        raise ValueError(f"unexpected input hash for default.xbe: {digest}")
    spans, ranges = declared_spans(payload)
    after, patch = holder.apply(payload)
    if not audit_digests(after):
        raise ValueError("a section digest does not match the repaired file")
    again, _ = holder.apply(after)
    if again != after:
        raise ValueError("the repair is not idempotent")
    scope = scope_receipt(payload, after, spans)
    return after, {"schema": SCHEMA, "job": "H1", "disc_file": DISC_FILE, "input_state": state,
                   "already_applied": state == "applied", "idempotent": True, "section_digests_valid": True,
                   "scope": scope, "declared_ranges": ranges, "owner": holder.OWNER,
                   "hook_va": hex(holder.HOOK_VA), "cave_va": hex(holder.CAVE_VA), "cave_code_bytes": holder.CODE_SIZE,
                   "rule": patch.get("rule"), "runtime_witnessed": False,
                   "files": {DISC_FILE: {"before_sha256": digest, "after_sha256": sha(after), "before_size": len(payload),
                                         "after_size": len(after)}},
                   "touched_disc_files": [DISC_FILE], "patch": {k: v for k, v in patch.items() if k != "edits"}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", required=True, type=Path, help="the disc's default.xbe (read only)")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-xbe-sha256", action="append", help="accept this stacked input hash (repeatable)")
    parser.add_argument("--accepted-input-hashes", type=Path, help="a previous receipt or {default.xbe: sha256} map")
    args = parser.parse_args(argv)
    source, out = args.xbe.resolve(), args.out_dir.resolve()
    if source.parent == out:
        raise ValueError("the output directory must differ from the read-only input directory")
    payload = read(source)
    after, receipt = repair(payload, accepted_hashes(args))
    out.mkdir(parents=True, exist_ok=True)
    write_new(out / DISC_FILE, after)
    text = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    receipt_path = out / "h1_receipt.json"
    write_new(receipt_path, text.encode("utf-8"))
    print(json.dumps({"status": "DONE", "output": str(out / DISC_FILE), "receipt": str(receipt_path),
                      "after_sha256": sha(after), "already_applied": receipt["already_applied"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
