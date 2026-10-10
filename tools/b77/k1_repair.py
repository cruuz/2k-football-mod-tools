#!/usr/bin/env python3
"""Native K1 repair of the v0.5 disc's default.xbe: spaces, periods, apostrophes and hyphens in player names.

Reads one disc file (``default.xbe``), writes a repaired copy and a receipt; no input is modified and no
disc image is opened.  The change is the Studio's ``nfl2k5_name_keyboard`` patch, applied to exactly the
bytes this job owns:

* ``.string_`` VA 0xEACAB0..0xEACB90 (file 0xB3B790, 224 bytes): the two retail letter lists and their
  padding become one 56-character list (A-Z a-z - ' space .), then zero padding,
* ``.text`` VA 0x3465BA (file 0x3365BA, 4 bytes): the Last Name keyboard's list pointer 0xEACB20 -> 0xEACAB0,
* the SHA-1 digest fields of ``.text`` and ``.string_`` in the XBE header (20 bytes each, derived from the
  whole section, so an integrator re-derives them after stacking every owner of those sections).

Everything else in the file is identical (checked by a scope receipt).  The file keeps its size.

default.xbe is shared with other b77 jobs.  Stacked input: pass that job's output with
``--expected-xbe-sha256 <its after_sha256>`` (repeatable) or ``--accepted-input-hashes <its receipt.json>``.
An input that already carries the patch is a recorded no-op.  Input whose edited bytes are neither retail nor
patched, or whose pinned keyboard code differs, is refused.  EXPERIMENTAL / UNWITNESSED in a played game.
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
from mod_editor.core import nfl2k5_name_keyboard as keyboard
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core.nfl2k5_bump_strength import _section_for_offset, _sections, section_digest

SCHEMA = "b77/k1_native_repair/v1"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
V05_FIXED_XBE_SHA256 = "a4280abd70ad2015f00510c3fc6ceb5d26decb756c907728cd44794696b7ad79"
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
    spans, sites = [], []
    for label, va, before, after in keyboard.SITES:
        offset = rdata.offset_of(payload, va)
        spans.append((offset, len(before)))
        sites.append({"label": label, "va": hex(va), "file_offset": hex(offset), "size": len(before),
                      "retail_sha256": sha(before), "patched_sha256": sha(after)})
    sections = _sections(payload)
    digests = []
    for _label, va, before, _after in keyboard.SITES:
        section = _section_for_offset(sections, rdata.offset_of(payload, va))
        if section.header_offset + 36 not in {o for o, _ in spans}:
            spans.append((section.header_offset + 36, 20))
            digests.append({"section_index": section.index, "section_va": hex(section.virtual_address),
                            "header_field_offset": hex(section.header_offset + 36), "size": 20,
                            "basis": "derived: SHA-1 of the whole section; re-derive after stacking owners"})
    return spans, sites + digests


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
    state = keyboard.status(payload)
    if state == "foreign":
        raise ValueError("default.xbe is not retail-shaped at the name keyboard sites, or its pinned keyboard code differs")
    if digest not in accepted and not (state == "applied" and digest == V05_FIXED_XBE_SHA256):
        raise ValueError(f"unexpected input hash for default.xbe: {digest}")
    spans, ranges = declared_spans(payload)
    after, patch = keyboard.apply(payload)
    if not audit_digests(after):
        raise ValueError("a section digest does not match the repaired file")
    again, _ = keyboard.apply(after)
    if again != after:
        raise ValueError("the repair is not idempotent")
    scope = scope_receipt(payload, after, spans)
    return after, {"schema": SCHEMA, "job": "K1", "disc_file": DISC_FILE, "input_state": state,
                   "already_applied": state == "applied", "idempotent": True, "section_digests_valid": True,
                   "scope": scope, "declared_ranges": ranges, "owner": keyboard.OWNER,
                   "character_lists_before": keyboard.allowed_characters(payload),
                   "character_lists_after": keyboard.allowed_characters(after),
                   "maximum_characters": keyboard.MAX_NAME_CHARACTERS, "runtime_witnessed": False,
                   "files": {DISC_FILE: {"before_sha256": digest, "after_sha256": sha(after), "before_size": len(payload),
                                         "after_size": len(after)}},
                   "touched_disc_files": [DISC_FILE], "patch": {k: v for k, v in patch.items() if k != "edits"}}


def native_summary(payload: bytes, after: bytes) -> dict:
    """Optional: the keyboard facts of both files from the game's own code under Unicorn."""
    sys.path.insert(0, str(ROOT))
    from tests.mod_editor import name_keyboard_probe as probe
    return {"before": probe.summary(payload), "after": probe.summary(after)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", required=True, type=Path, help="the disc's default.xbe (read only)")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-xbe-sha256", action="append", help="accept this stacked input hash (repeatable)")
    parser.add_argument("--accepted-input-hashes", type=Path, help="a previous receipt or {default.xbe: sha256} map")
    parser.add_argument("--native-proof", action="store_true", help="embed the Unicorn keyboard summary (needs unicorn)")
    args = parser.parse_args(argv)
    source, out = args.xbe.resolve(), args.out_dir.resolve()
    if source.parent == out:
        raise ValueError("the output directory must differ from the read-only input directory")
    payload = read(source)
    after, receipt = repair(payload, accepted_hashes(args))
    if args.native_proof:
        receipt["native_summary"] = native_summary(payload, after)
    out.mkdir(parents=True, exist_ok=True)
    write_new(out / DISC_FILE, after)
    text = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    receipt_path = out / "k1_receipt.json"
    write_new(receipt_path, text.encode("utf-8"))
    print(json.dumps({"status": "DONE", "output": str(out / DISC_FILE), "receipt": str(receipt_path),
                      "after_sha256": sha(after), "already_applied": receipt["already_applied"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
