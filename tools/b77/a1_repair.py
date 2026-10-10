#!/usr/bin/env python3
"""b77 / a1 native repair of the v0.5 default.xbe: the 25th Anniversary list draws the moment a click opens.

Beta 76.5 sorted the 51 moments by date by mapping the list's display row to the physical SITU row, but only in the
select handler, the completed-moment test, the restored highlight and the caption function 20C350 (which retail never
calls). The rows the player sees are drawn by 20C800 (title and date) and 20C710 / 20C790 (mini helmets), which read
their SITU record with the raw display row: 27 of the 51 rows showed one moment and opened another. This repair points
the four `call 2CFD40` sites of those callbacks at the owner's existing display helper.

Disc files touched: `default.xbe` only. Declared ranges (every other byte must be identical):
  * the four rel32 operands at VA 0x20C71F, 0x20C741, 0x20C79C, 0x20C814 (raw = VA - 0x10000), 16 bytes in all;
  * the SHA-1 digest of the one section those bytes sit in (.text), 20 bytes in its section header.

The input must be the v0.5 executable (sha256 below) or a file named in --accepted-input-hashes (a stacked input from
another job's repair, or a previous receipt of this one); either way the Anniversary owner must read "applied" with
the row hooks "previous" (or already "applied": then the output is the input, byte for byte). Deterministic,
idempotent, writes new files only. No gameplay is run; the proof is tests/mod_editor/test_b77_a1_menu_identity.py.

  python3 tools/b77/a1_repair.py --input-dir DIR_WITH_default.xbe --output-dir NEW_DIR [--accepted-input-hashes JSON]
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
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_espn25_more_moments as mm  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

V05_XBE_SHA256 = "2b0fbbbb89b5c72aaed7c454bf6e78dd2c97f1e417e2d761e515907ed81471ab"      # SOFTDRINK 2K28 v0.5
V05_XBE_SIZE = 12300288
FIXED_XBE_SHA256 = "eb7690995093216e7c1e167163ade06306cc25eea12a7d6b0d230aabb89acf4b"    # the repair of exactly that file
NAME = "default.xbe"
SCHEMA = "b77/a1_native_repair/v1"
MAX_XBE = 16 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read(MAX_XBE + 1)


def write_new(path, raw):
    """New files only: an identical existing file is accepted (replay), a different one is never replaced."""
    path = Path(path)
    if path.exists():
        mm.require(read(path) == raw, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def accepted_hashes(path):
    """The v0.5 hash, plus (when given) the sha256 of default.xbe from an explicit manifest: a JSON object
    {"default.xbe": "<sha256>"} or {"files": {"default.xbe": "<sha256>" | {"sha256"|"after_sha256": ...}}}, which is
    also the shape of this tool's own receipt."""
    result = {V05_XBE_SHA256}
    if path is None:
        return result
    doc = json.loads(read(path))
    mm.require(isinstance(doc, dict), "accepted input manifest must be an object")
    files = doc.get("files", doc)
    mm.require(isinstance(files, dict) and NAME in files, "accepted input manifest needs default.xbe")
    row = files[NAME]
    mm.require(isinstance(row, (str, dict)), "invalid accepted default.xbe row")
    digest = row if isinstance(row, str) else row.get("sha256", row.get("after_sha256"))
    mm.require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), "invalid accepted SHA-256")
    result.add(digest)
    return result


def declared_ranges(payload):
    """[(raw start, raw end, label)] this repair may change in `payload`."""
    code, dat = mm.allocations(payload)
    image = XbeImage(payload)
    rows = [edit for edit in mm.sites(code["va"], dat["va"], 51) if edit[0] in mm.ROW_LABELS]
    mm.require(len(rows) == len(mm.ROW_HOOKS), "row-draw hook sites")
    out = []
    for label, va, before, _after in rows:
        at = image.offset(va, len(before))
        out.append((at + 1, at + 5, f"{label}: rel32 of the call at VA {va:#x}"))
    holding = [s for s in _sections(payload)
               if any(s.raw_offset <= start < s.raw_offset + s.raw_size for start, _end, _label in out)]
    mm.require(len(holding) == 1 and all(holding[0].raw_offset <= start and end <= holding[0].raw_offset + holding[0].raw_size
                                         for start, end, _label in out), "the four hook sites must sit in one section")
    out.append((holding[0].header_offset + 36, holding[0].header_offset + 56,
                f"SHA-1 digest of section {holding[0].index}, which holds them"))
    return out


def scope_receipt(before, after, ranges):
    """Every changed byte must lie in a declared range; returns the exact runs with their hashes."""
    mm.require(len(before) == len(after), "the executable changed size")
    inside = bytearray(len(before))
    for start, end, _label in ranges:
        inside[start:end] = b"\1" * (end - start)
    changed = [i for i in range(len(before)) if before[i] != after[i]]
    outside = [i for i in changed if not inside[i]]
    if outside:
        raise mm.MoreMomentsError(f"out-of-scope byte changed at raw {outside[0]:#x}")
    rows = []
    for start, end, label in ranges:
        rows.append(dict(raw_start=start, raw_end=end, label=label, before_hex=before[start:end].hex(),
                         after_hex=after[start:end].hex(), before_sha256=sha(before[start:end]),
                         after_sha256=sha(after[start:end]), changed=before[start:end] != after[start:end]))
    return dict(changed_bytes=len(changed), outside_scope_identical=True, declared_ranges=rows,
                declared_bytes=sum(end - start for start, end, _l in ranges))


def repair(payload, data=None):
    """(fixed bytes, receipt body). Refuses anything the Anniversary owner does not recognise."""
    data = mm.Data.load() if data is None else data
    mm.require(mm.status(payload, data) == "applied", "the Anniversary moments owner is not an applied install")
    state = mm.row_hooks_status(payload, data)
    mm.require(state in ("previous", "applied"), f"row-draw hooks are {state}")
    ranges = declared_ranges(payload)
    fixed, moments = mm.apply(payload, data)
    mm.require(mm.row_hooks_status(fixed, data) == "applied" and mm.status(fixed, data) == "applied",
               "the repaired executable is not recognised")
    scope = scope_receipt(payload, fixed, ranges)
    if state == "applied":
        mm.require(fixed == payload, "an already repaired executable must come back unchanged")
    else:
        mm.require(scope["changed_bytes"] == 36 and moments["status"] == "upgraded", "unexpected repair size")
    return fixed, dict(status="already_repaired" if state == "applied" else "repaired", scope=scope,
                       moments_owner=dict(status=moments["status"], rows=moments.get("rows"),
                                          edits=moments.get("edits", [])))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", required=True, type=Path, help="a folder holding the v0.5 default.xbe")
    parser.add_argument("--output-dir", required=True, type=Path, help="a new folder for the repaired default.xbe")
    parser.add_argument("--accepted-input-hashes", type=Path, help="stacked input: {'default.xbe': sha256} or a receipt")
    args = parser.parse_args(argv)
    source, output = args.input_dir.resolve(), args.output_dir.resolve()
    mm.require(source != output, "output directory must differ from the read-only input")
    accepted = accepted_hashes(args.accepted_input_hashes)
    payload = read(source / NAME)
    mm.require(len(payload) <= MAX_XBE, "default.xbe is larger than 16 MiB")
    mm.require(sha(payload) in accepted, "unexpected input hash: " + NAME)
    fixed, body = repair(payload)
    again, replay = repair(fixed)                       # idempotence before anything is written
    mm.require(again == fixed and replay["status"] == "already_repaired", "the repair is not idempotent")
    if sha(payload) == V05_XBE_SHA256:
        mm.require(sha(fixed) == FIXED_XBE_SHA256 and len(payload) == V05_XBE_SIZE, "unexpected repair of the v0.5 file")
    receipt = dict(schema=SCHEMA, job="a1", runtime_witnessed=False, idempotent=True,
                   touched_disc_files=[NAME], accepted_input_manifest=bool(args.accepted_input_hashes),
                   files={NAME: dict(before_sha256=sha(payload), after_sha256=sha(fixed),
                                     before_size=len(payload), after_size=len(fixed))},
                   replay_status=replay["status"], **body)
    output.mkdir(parents=True, exist_ok=True)
    write_new(output / NAME, fixed)
    write_new(output / "a1_receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"status": "DONE", "output": str(output), "receipt": str(output / "a1_receipt.json"),
                      "before_sha256": sha(payload), "after_sha256": sha(fixed)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
