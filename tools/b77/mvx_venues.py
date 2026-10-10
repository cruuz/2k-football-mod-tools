#!/usr/bin/env python3
"""Compile and repair moment-only stadium selections, retaining all existing art.

The physical stadium word controls environment metadata. The installed mode-8
filename hook still loads a00..a50, regardless of that word's source prefix.
Input/output are loose situation.iff files, never a disc or an archive pack.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_espn25_fields as fields

PLAN = ROOT / "data/nfl2k5_moment_venue_selections.json"
MAX_SITU = 4 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def plan():
    doc = json.loads(PLAN.read_text(encoding="utf-8"))
    require(doc.get("schema") == "b77/mvx_venue_selections/v1", "foreign selection plan")
    rows = doc["selections"]
    require([r["row"] for r in rows] == list(range(1, 52)), "expected all 51 physical rows")
    for r in rows:
        require(all(type(r[k]) is int and 0 <= r[k] < 82 for k in ("before", "after")), "invalid stadium index")
    return doc


def compile_catalog():
    """Use the existing field compiler's table; aliases, donors and art stay fixed."""
    doc = json.loads(fields.DATA.read_text(encoding="utf-8"))
    for row, decision in zip(fields.catalog(), plan()["selections"]):
        require(all(row[k] == decision[k] for k in ("row", "date", "title", "source_kind", "source_prefix")),
                "selection plan belongs to a different moment or bundle")
        require(row["native_stadium_index"] in (decision["before"], decision["after"]), "foreign catalog selection")
        target = doc["moments"][row["row"] - 1]
        target["native_stadium_index"] = decision["after"]
        if decision["before"] != decision["after"]:
            target["previous_native_stadium_index"] = decision["before"]
            target["selection_note"] = decision["reason"]
    return json.dumps(doc, indent=2) + "\n"


def repair(raw, *, expected_input_sha256=None):
    """Hash-gated, fixed-size rewrite with a byte-for-byte outside-scope check."""
    require(32 + 0x44 + 51 * 0x6C <= len(raw) <= MAX_SITU, "invalid situation size")
    require(raw[:4] == b"SITU" and struct.unpack_from("<I", raw, 8)[0] == 51
            and struct.unpack_from("<I", raw, 32 + 0x40)[0] == 51, "expected 51-row SITU")
    doc = plan()
    require(compile_catalog() == fields.DATA.read_text(encoding="utf-8"), "compile the selection catalog first")
    rows = doc["selections"]
    offsets = [32 + 0x44 + (r["row"] - 1) * 0x6C + 0x10 for r in rows]
    values = [struct.unpack_from("<I", raw, at)[0] for at in offsets]
    before = [r["before"] for r in rows]
    after = [r["after"] for r in rows]
    require(values in (before, after), "foreign or mixed moment selection profile")
    # Normalize only our selection words before comparing with the exact final
    # v0.6 input. This admits our own output while refusing unrelated mutations.
    normalized = bytearray(raw)
    for at, value in zip(offsets, before):
        struct.pack_into("<I", normalized, at, value)
    require(sha(normalized) == doc["baseline_situation_sha256"] or
            (expected_input_sha256 is not None and sha(raw) == expected_input_sha256),
            "unrecognized input hash; a stacked input needs its explicit expected SHA-256")
    result, compiler_receipt = fields.repair_situ(raw)
    restored = bytearray(result)
    edits = []
    for row, at, old, new in zip(rows, offsets, values, after):
        require(struct.unpack_from("<I", result, at)[0] == new, "selection read-back failed")
        restored[at:at + 4] = raw[at:at + 4]
        if old != new:
            edits.append(dict(row=row["row"], offset=at, size=4, before=old, after=new))
    require(bytes(restored) == raw and len(result) == len(raw), "repair escaped selection words")
    return result, dict(schema="b77/mvx_native_repair/v1", before_sha256=sha(raw), after_sha256=sha(result),
                        changed_bytes=sum(a != b for a, b in zip(raw, result)), edits=edits,
                        outside_scope_identical=True, rows_verified=51,
                        scope="situation.iff only, physical record +0x10 stadium dwords",
                        compiler_receipt=compiler_receipt)


def write_new(path, raw):
    require(not path.exists(), "output already exists")
    with path.open("xb") as handle:
        handle.write(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("compile")
    sub.add_parser("check")
    cmd = sub.add_parser("repair")
    cmd.add_argument("--input", type=Path, required=True)
    cmd.add_argument("--output-dir", type=Path, required=True)
    cmd.add_argument("--expected-input-sha256")
    args = parser.parse_args(argv)
    if args.command == "compile":
        fields.DATA.write_text(compile_catalog(), encoding="utf-8", newline="\n")
    elif args.command == "check":
        require(compile_catalog() == fields.DATA.read_text(encoding="utf-8"), "selection catalog differs")
        print("consistent: 51 moments, existing aliases and art")
    else:
        require(args.input.stat().st_size <= MAX_SITU, "input exceeds bounds")
        raw, receipt = repair(args.input.read_bytes(), expected_input_sha256=args.expected_input_sha256)
        require(not args.output_dir.exists(), "output directory already exists")
        args.output_dir.mkdir(parents=True)
        write_new(args.output_dir / "situation.iff", raw)
        (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps(receipt))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
