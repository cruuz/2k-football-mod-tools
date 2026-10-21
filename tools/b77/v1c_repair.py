#!/usr/bin/env python3
"""V1C: repair the v0.6 executable and SITU entry in new files only.

The coordinator may apply repair_xbe / repair_situation to a stacked byte
buffer. The CLI pins complete input hashes, with explicit accepted hashes for
stacked inputs. Both pure transforms also validate their owned instructions or
scenario fields. No disc, retail resource or input file is overwritten.
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
from mod_editor.core import nfl2k5_era_rules as era
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

V06_HASHES = {
    "default.xbe": "f67e6fc1cb76c9ea1f1ad504e4a6491ff126483d66a9da8ddb92950bbaf740ba",
    "situation.iff": "552f898ab50ecef646301f29c5c94495a9c69c0de91ea89c7bcdd26bf6f4429b",
}
SITU_PACK0_OFFSET = 13312000
ROW34 = 32 + 0x44 + 33 * 0x6C
# Exact state before Brady's first play, nflverse 2003_21_CAR_NE / 4297.
SITU_FIELDS = ((0x24, "I", 0, 1, "user side"),
               (0x28, "I", 0, 1, "possession"),
               (0x2C, "I", 22, 29, "Carolina score"),
               (0x40, "f", 30.0, -10.0, "ball at NE 40"),
               (0x4C, "f", 163.0, 68.0, "clock 1:08"),
               (0x50, "I", 3, 2, "Carolina timeouts"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def scope(before, after, ranges):
    era.require(len(before) == len(after), "repair changed file length")
    ranges = sorted(ranges)
    cursor = 0
    changed = 0
    rows = []
    for lo, hi, label in ranges:
        era.require(cursor <= lo < hi <= len(before), "overlapping or invalid scope")
        era.require(before[cursor:lo] == after[cursor:lo], "out-of-scope bytes changed")
        count = sum(a != b for a, b in zip(before[lo:hi], after[lo:hi]))
        changed += count
        rows.append(dict(start=lo, end=hi, label=label, before_sha256=sha(before[lo:hi]),
                         after_sha256=sha(after[lo:hi]), changed_bytes=count))
        cursor = hi
    era.require(before[cursor:] == after[cursor:], "out-of-scope tail changed")
    return dict(before_sha256=sha(before), after_sha256=sha(after), size=len(after),
                changed_bytes=changed, outside_scope_identical=True, ranges=rows)


def repair_xbe(raw):
    era.require(era.status(raw) == "applied", "expected recognized Anniversary era rules")
    owned = era.places(raw)
    image = XbeImage(raw)
    result, _ = era.apply(raw)
    ranges = [(owned[k]["raw"], owned[k]["raw"] + owned[k]["size"], "era " + k)
              for k in ("code", "read_only")]
    # Existing hook locations are unchanged. Only the new classifier is added.
    at = image.offset(0x22DFF0, 7)
    ranges.append((at, at + 7, "successful try event classifier"))
    ranges += [(space.DIRECTORY + 20, space.DIRECTORY + 52, "directory SHA-256"),
               (space.SCALE_DIRECTORY + 12, space.SCALE_DIRECTORY + 76, "code and read-only seals")]
    # Digests are the only mutable fields in affected section descriptors.
    changed_sections = [s for s in _sections(raw)
        if raw[s.raw_offset:s.raw_offset + s.raw_size] != result[s.raw_offset:s.raw_offset + s.raw_size]]
    ranges += [(s.header_offset + 36, s.header_offset + 56, "section digest " + str(s.index))
               for s in changed_sections]
    receipt = scope(raw, result, ranges)
    receipt["revision"] = 2
    return result, receipt


def repair_situation(raw):
    era.require(len(raw) == 151520 and struct.unpack_from("<I", raw, 8)[0] == 51,
                "expected v0.6 51-row situation.iff")
    # The title/team pointers can move when text is rebuilt. Check identities
    # through the field-relative pointers before touching scalar state.
    from mod_editor.core import nfl2k5_espn25_more_moments as mm
    body = raw[32:32 + struct.unpack_from("<I", raw, 4)[0]]
    for offset, expected in ((0, "SUPER BOWL XXXVIII: FINALE"), (20, "panthers"), (24, "patriots")):
        field = ROW34 - 32 + offset
        era.require(mm.sc.utf16(body, mm.sc.rel(body, field)) == expected, "unexpected row 34 identity")
    values = [struct.unpack_from("<" + fmt, raw, ROW34 + off)[0]
              for off, fmt, _before, _after, _label in SITU_FIELDS]
    before = [r[2] for r in SITU_FIELDS]
    after = [r[3] for r in SITU_FIELDS]
    era.require(values == before or values == after, "mixed or foreign row 34 state")
    out = bytearray(raw)
    for off, fmt, _before, value, _label in SITU_FIELDS:
        struct.pack_into("<" + fmt, out, ROW34 + off, value)
    result = bytes(out)
    receipt = scope(raw, result, [(ROW34 + off, ROW34 + off + 4, label)
                                  for off, _fmt, _b, _a, label in SITU_FIELDS])
    receipt["pack0_ranges"] = [[SITU_PACK0_OFFSET + r["start"], SITU_PACK0_OFFSET + r["end"]]
                               for r in receipt["ranges"]]
    receipt["outer_index"] = 22
    return result, receipt


def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        result = stream.read(16 * 1024 * 1024 + 1)
    era.require(len(result) <= 16 * 1024 * 1024, "oversized input")
    return result


def write_new(path, raw):
    if path.exists():
        era.require(read(path) == raw, "refusing different existing output: " + str(path))
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--accepted-input-hashes", type=Path)
    args = parser.parse_args(argv)
    era.require(args.input_dir.resolve() != args.output_dir.resolve(), "choose a new output directory")
    accepted = {name: {digest} for name, digest in V06_HASHES.items()}
    if args.accepted_input_hashes:
        doc = json.loads(read(args.accepted_input_hashes))
        for name, value in doc.get("files", doc).items():
            era.require(name in accepted, "unknown accepted input file")
            accepted[name].add(value if isinstance(value, str) else value["after_sha256"])
    pending, receipts = {}, {}
    for name, repair in (("default.xbe", repair_xbe), ("situation.iff", repair_situation)):
        raw = read(args.input_dir / name)
        era.require(sha(raw) in accepted[name], "unexpected input hash: " + name)
        pending[name], receipts[name] = repair(raw)
        era.require(repair(pending[name])[0] == pending[name], "repair is not idempotent")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in pending.items():
        write_new(args.output_dir / name, raw)
    doc = dict(schema="b771/v1c/native-repair/v1", files=receipts, idempotent=True,
               runtime_witnessed=False, disc_files=["default.xbe", "vc_53450030/0 (outer 22 only)"])
    write_new(args.output_dir / "receipt.json", (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({name: {k: row[k] for k in ("after_sha256", "changed_bytes")}
                      for name, row in receipts.items()}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
