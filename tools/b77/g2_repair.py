#!/usr/bin/env python3
"""Native G2 repair of the v0.5 disc's default.xbe: right-stick moves and charge-ups only for starred players.

Reads one disc file (``default.xbe``), writes a repaired copy and a receipt; no input is modified and no disc image
is opened.  The change is the Studio's abilities owner (``nfl2k5_abilities_runtime``) moving from the beta 76.5
template to the star-gate template with the SOFTDRINK defaults: ``right_stick_stars_only`` and
``charge_stars_only`` on, ``button_moves_stars_only`` off (face-button moves stay open to every player), and the
default access table (starred with no ability tier: stick juke flicks and charge-ups; Star tier: plus stutter-step and
stop short; Superstar and X-Factor tiers: everything including the stick-click hurdle).  Every switch and the table
can be changed on the command line.  It touches only bytes that owner already owns:

* the owner's own 1344-byte allocation (VA 0x14DA000, file 0xB8A000): the flag reader (now adding the star's access
  grants), a few words of the command table (the stick commands 0x1A and 0x24..0x2B gain grant bits in their required
  mask), two descriptor-family masks, the four-byte access table that was padding, and with the charge rule four
  edits inside ``maintain``.  Hooks, labels of every hook target, the permission word at 0x14DA508 and every other
  owner are untouched (all eight hook displacements are byte-identical because the new template keeps the v0.5
  label positions).
* the derived integrity fields that cover those bytes: the allocator's RX SHA-256 and directory SHA-256 and the
  SHA-1 digest field of each XBE section that holds a changed byte.  These are recomputed from the input, never
  copied, so an integrator re-derives them after stacking every owner.

Everything else in the file is identical (checked by a scope receipt).  The file keeps its size.

default.xbe is shared with other b77 jobs.  Stacked input: pass that job's output with
``--expected-xbe-sha256 <its after_sha256>`` (repeatable) or ``--accepted-input-hashes <its receipt.json>``.
An input that already carries the star gate with the same settings is a recorded no-op.  Input whose owner,
dependencies or seals are not the v0.5 ones (or this revision) is refused.  EXPERIMENTAL / UNWITNESSED in a
played game.
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
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

SCHEMA = "b77/g2_native_repair/v1"
DISC_FILE = "default.xbe"
V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"
# Result for the v0.5 input with the default settings; set from a run, asserted by
# tests/mod_editor/test_b77_g2_repair.py against the real v0.5 file when NFL2K5_V05_XBE points at it.
V05_DEFAULT_RESULT_SHA256 = "09c65337c640016cfc49c443e170fc1891c1da6bf5add1619eb6ee8aaf01fb34"


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
    """The bytes this repair may write, decided from the input alone (never from what changed)."""
    allocation = abilities.allocation(payload)
    image = XbeImage(payload)
    spans = [(allocation["raw"], allocation["size"])]
    labels = [dict(label="abilities owner allocation (flag reader, command table, family masks)",
                   va=hex(allocation["va"]), file_offset=hex(allocation["raw"]), size=allocation["size"],
                   basis="the owner's own reserved code; hooks, labels and the permission word are not edited")]
    seals = [(space.SCALE_DIRECTORY + 12, 32, "allocator RX SHA-256"),
             (space.DIRECTORY + len(space.SCALE_TAG) + 8, 32, "allocator directory SHA-256")]
    for at, size, name in seals:
        spans.append((at, size))
        labels.append(dict(label=name, file_offset=hex(at), size=size,
                           basis="derived: recomputed from the whole RX content; re-derive after stacking owners"))
    for section in image.sections:
        holds = [at for at, _size in spans if section.raw <= at < section.raw + section.raw_size]
        if holds:
            field = section.header + 36
            spans.append((field, 20))
            labels.append(dict(label=f"{section.name} section SHA-1", file_offset=hex(field), size=20,
                               basis="derived: SHA-1 of the whole section; re-derive after stacking owners"))
    spans.sort()
    return spans, labels


def runs(before: bytes, after: bytes, lo: int, hi: int) -> list[tuple[int, int]]:
    """Maximal runs of differing bytes inside [lo, hi)."""
    out, start = [], None
    for i in range(lo, hi):
        if before[i] != after[i]:
            if start is None:
                start = i
        elif start is not None:
            out.append((start, i - start))
            start = None
    if start is not None:
        out.append((start, hi - start))
    return out


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


def repair_xbe(payload: bytes, accepted: set[str] | None = None, *, right_stick_stars_only: bool = True,
               charge_stars_only: bool = True, button_moves_stars_only: bool = False,
               star_access=abilities.DEFAULT_STAR_ACCESS) -> tuple[bytes, dict]:
    """The v0.5 (or already star-gated) executable with the star gate installed as asked."""
    digest = sha(payload)
    if accepted is not None and digest not in accepted:
        state = abilities.revision(payload)
        if state != "star-gate":
            raise ValueError(f"unexpected input hash for default.xbe: {digest}")
    state, settings, revision = abilities._inspect_revision(payload)
    if state != "applied" or not space.is_scaleout(payload):
        raise ValueError("expected the installed abilities rules v2 owner on the sealed v3 allocator")
    if revision not in ("beta-76.5", "star-gate"):
        raise ValueError(f"unexpected abilities revision {revision!r}")
    allocation = abilities.allocation(payload)
    raw, size = allocation["raw"], allocation["size"]
    wanted = dict(settings, right_stick_stars_only=bool(right_stick_stars_only),
                  charge_stars_only=bool(charge_stars_only), button_moves_stars_only=bool(button_moves_stars_only),
                  star_access=tuple(star_access))
    old_content = payload[raw:raw + size]
    new_content, _labels = abilities.code_for(allocation["va"], **wanted)
    spans, ranges = declared_spans(payload)
    requests = space._read_scale_directory(payload)
    buf = bytearray(payload)
    buf[raw:raw + size] = new_content
    if old_content != new_content:
        space._seal_scaleout(buf, requests)
        touched = [i for i in range(len(buf)) if buf[i] != payload[i]]
        for section in _sections(buf):
            if any(section.raw_offset <= i < section.raw_offset + section.raw_size for i in touched):
                buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
    result = bytes(buf)
    after_state, after_settings, after_revision = abilities._inspect_revision(result)
    if (after_state, after_revision) != ("applied", "star-gate") or any(
            after_settings[k] != wanted[k] for k in wanted):
        raise ValueError("star gate postcondition failed")
    if space._read_scale_directory(result) != requests:
        raise ValueError("allocator requests changed")
    again, _ = abilities.apply(result, right_stick_stars_only=wanted["right_stick_stars_only"],
                               charge_stars_only=wanted["charge_stars_only"],
                               button_moves_stars_only=wanted["button_moves_stars_only"],
                               star_access=wanted["star_access"])
    if again != result:
        raise ValueError("the repair is not idempotent")
    scope = scope_receipt(payload, result, spans)
    changed_runs = [dict(file_offset=hex(o), size=n, owner_offset=o - raw,
                         before=payload[o:o + n].hex(), after=result[o:o + n].hex())
                    for o, n in runs(payload, result, raw, raw + size)]
    return result, {"schema": SCHEMA, "job": "G2", "disc_file": DISC_FILE,
                    "input_state": revision, "already_applied": old_content == new_content,
                    "idempotent": True, "scope": scope, "declared_ranges": ranges,
                    "owner": abilities.OWNER, "owner_allocation": {k: (hex(v) if isinstance(v, int) and k in ("va", "raw") else v)
                                                                   for k, v in allocation.items()},
                    "settings_before": {k: settings[k] for k in sorted(settings)},
                    "settings_after": {k: after_settings[k] for k in sorted(after_settings)},
                    "owner_changed_runs": changed_runs,
                    "owner_changed_bytes": sum(r["size"] for r in changed_runs),
                    "allocator_requests_unchanged": True, "hooks_unchanged": True,
                    "runtime_witnessed": False,
                    "files": {DISC_FILE: {"before_sha256": digest, "after_sha256": sha(result),
                                          "before_size": len(payload), "after_size": len(result)}},
                    "touched_disc_files": [DISC_FILE]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--xbe", required=True, type=Path, help="the disc's default.xbe (read only)")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-xbe-sha256", action="append", help="accept this stacked input hash (repeatable)")
    parser.add_argument("--accepted-input-hashes", type=Path, help="a previous receipt or {default.xbe: sha256} map")
    parser.add_argument("--no-right-stick-stars-only", action="store_true",
                        help="leave right-stick moves open to everyone (installs the revision only)")
    parser.add_argument("--no-charge-stars-only", action="store_true",
                        help="leave the charge-up meter open to everyone")
    parser.add_argument("--button-moves-stars-only", action="store_true",
                        help="also make spin, truck, stiff-arm and button jukes star-only (default off)")
    parser.add_argument("--star-access", default=",".join(abilities.DEFAULT_STAR_ACCESS),
                        help="four levels: starred no tier, Star, Superstar, X-Factor; one of "
                             + ", ".join(abilities.ACCESS_LEVELS))
    args = parser.parse_args(argv)
    source, out = args.xbe.resolve(), args.out_dir.resolve()
    if source.parent == out:
        raise ValueError("the output directory must differ from the read-only input directory")
    payload = read(source)
    after, receipt = repair_xbe(payload, accepted_hashes(args), right_stick_stars_only=not args.no_right_stick_stars_only,
                                charge_stars_only=not args.no_charge_stars_only,
                                button_moves_stars_only=args.button_moves_stars_only,
                                star_access=tuple(args.star_access.split(",")))
    out.mkdir(parents=True, exist_ok=True)
    write_new(out / DISC_FILE, after)
    text = json.dumps(receipt, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    receipt_path = out / "g2_receipt.json"
    write_new(receipt_path, text.encode("utf-8"))
    print(json.dumps({"status": "DONE", "output": str(out / DISC_FILE), "receipt": str(receipt_path),
                      "after_sha256": sha(after), "already_applied": receipt["already_applied"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
