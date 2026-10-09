#!/usr/bin/env python3
"""b77 / a3 + a5 native repair of the v0.5 situation.iff: each 25th Anniversary moment selects its sourced uniform style.

In v0.5 every authored "kit 0" was moved to the franchise's spare style (the retail 2004 look), so the newer moments (the
Unc Bowl, the 2012-2025 Super Bowls ...) showed 2004 stock jerseys. This repair changes ONLY which style a moment side
selects: the 4-byte kit index at +0x58 (away) / +0x5C (home) of a SITU record. Slot contents (styles, kit files, art) are
never touched. The new indexes come from the `decisions` block of data/nfl2k5_moment_uniform_eras.json (compiled by
tools/b77/a1_uniforms.py from the sourced uniform eras): style 0, the 2026 kit, for the sides whose current look is what
the team wore that season; the retail 2004 kit and retail period sets stay where they are period-correct.

Disc file touched: situation.iff (outer 22 of the archive, name id 0x3F407CF4, lives in PACK0), same size. Declared
ranges: the 4-byte kit index of every side whose decision differs from the shipped value (raw offset in the file =
32 + 0x44 + 0x6C * row + 0x58 or 0x5C; 0-based physical row). Every other byte must be identical.

The input must be the v0.5 file (sha256 below), the a1x output (the first version of this repair, 8e71ed69...), or a file named
in --accepted-input-hashes (a stacked input or a previous receipt). All 52 authored sides must read the shipped kit (state
v05), or all the kit a1x wrote (state a1x: the a1x repair was already applied, the a5 selection is applied on top of it), or all
the a5 kits, or all the new kits (applied: the output equals the input); a mixture is refused. a5 changed the rules (R3 without the
template cutoff, sourced R0 overrides): Patriots 2014-17, Falcons 2016 and Ravens 2012 go back to the retail 2004 look, the
Giants road, Cardinals 2008, Lions 2015 too, Eagles 2010 away to style 10 and the 2021 Rams to style 2.
a5k adds five native period kits and eight R0 selections across six moments, including both worn Unc Bowl sets. Deterministic, idempotent, writes new files only.

  python3 tools/b77/a1_uniforms_repair.py --input-dir DIR_WITH_situation.iff --output-dir NEW_DIR [--accepted-input-hashes JSON]
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
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
import a1_uniforms as uni  # noqa: E402

NAME = "situation.iff"
V05_SITU_SHA256 = "c995bd16fedf4ac0961564981af5316f6df2c626cf46d07ee0edbcee3ec3ebd2"   # outer 22 of the v0.5 disc
V05_SITU_SIZE = 151520
A1X_SITU_SHA256 = "8e71ed6925ec91ffd5bc1c06a963bcdb79266fce1629f5337bc4856a9436fb62"   # the a1x repair's output on the v0.5 file
A5_SITU_SHA256 = "3570ae91019e932e0b632885c4968670b440c11a7a349c7fb0b0dc581f6b2edb"
SCHEMA = "b77/a3_native_repair/v2"
OLD_SCHEMAS = ("b77/a3_native_repair/v1", SCHEMA)
MAX_SITU = 4 * 1024 * 1024


class UniformRepairError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise UniformRepairError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read(MAX_SITU + 1)


def write_new(path, raw):
    path = Path(path)
    if path.exists():
        require(read(path) == raw, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def accepted_hashes(path):
    result = {V05_SITU_SHA256, A1X_SITU_SHA256, A5_SITU_SHA256}
    if path is None:
        return result
    doc = json.loads(read(path))
    if isinstance(doc, dict) and doc.get("schema") in OLD_SCHEMAS and isinstance(doc.get("after_sha256"), str):
        return result | {doc["after_sha256"]}                 # this tool's own receipt: a verified replay
    files = doc.get("files", doc) if isinstance(doc, dict) else None
    require(isinstance(files, dict) and NAME in files, "accepted input manifest needs situation.iff")
    row = files[NAME]
    if isinstance(row, dict):
        row = row.get("sha256") or row.get("after_sha256")
    require(isinstance(row, str) and len(row) == 64, "invalid accepted situation.iff row")
    return result | {row}


def table(eras):
    """[(row, side, v0.5 kit, new kit, raw offset, a1x kit)] for the 52 authored sides, from the eras file's decisions."""
    rows = []
    for d in eras["decisions"]:
        at = 32 + uni.SITU_ROW[0] + uni.SITU_ROW[1] * d["situ_row"] + uni.KIT_AT[d["side"]]
        rows.append((d["situ_row"], d["side"], d["v05_kit"], d["v06_kit"], at, d.get("a1x_kit", d["v05_kit"])))
    require(len(rows) == 52 and len({(r, s) for r, s, *_ in rows}) == 52, "the decisions must cover 26 moments x 2 sides")
    return rows


def transform(raw, eras):
    """(new bytes, receipt) for one situation.iff; refuses a file that is not, on all 52 sides, the v0.5 kits, the a1x kits or the
    new kits (a mixture or a foreign file)."""
    require(len(raw) == V05_SITU_SIZE, "not the v0.5 situation.iff size")
    kits = uni.read_situ_kits(raw)
    rows = table(eras)
    require(len({r for r, _s in kits}) == 51, "the file does not hold the 51 moment rows")
    at_new = all(kits[(r, s)] == after for r, s, _b, after, _o, _x in rows)
    at_v05 = all(kits[(r, s)] == before for r, s, before, _a, _o, _x in rows)
    at_a1x = all(kits[(r, s)] == a1x for r, s, _b, _a, _o, a1x in rows)
    a5 = {(d['situ_row'], d['side']): d.get('a5_kit', d['v06_kit']) for d in eras['decisions']}
    at_a5 = all(kits[k] == value for k, value in a5.items())
    require(at_new or at_v05 or at_a1x or at_a5,
            "situation.iff holds neither the v0.5, a1x, a5 nor new kits on every authored side (mixed or foreign)")
    state = "applied" if at_new else ("v05" if at_v05 else ("a1x" if at_a1x else "a5"))
    out = bytearray(raw)
    changed = []
    if not at_new:
        for r, s, before, after, at, a1x in rows:
            current = before if at_v05 else (a1x if at_a1x else a5[(r, s)])
            if current != after:
                require(struct.unpack_from("<I", out, at)[0] == current, f"row {r + 1} {s}: kit changed under the repair")
                struct.pack_into("<I", out, at, after)
                changed.append(dict(row=r + 1, side=s, offset=at, before=current, after=after,
                                    before_hex=struct.pack("<I", current).hex(), after_hex=struct.pack("<I", after).hex()))
    result = bytes(out)
    declared = {c["offset"] + k for c in changed for k in range(4)}
    diff = {i for i in range(len(raw)) if raw[i] != result[i]}
    require(diff <= declared and len(result) == len(raw), "the repair changed bytes outside its declared ranges")
    kits_after = uni.read_situ_kits(result)
    require(all(kits_after[(r, s)] == after for r, s, _b, after, _o, _x in rows), "read-back differs from the decisions")
    require(all(kits_after[k] == v for k, v in kits.items() if k[0] < uni.RETAIL_COUNT), "a retail row changed")
    return result, dict(before_sha256=sha(raw), after_sha256=sha(result), size=len(raw), bytes_changed=len(diff),
                        declared_bytes=len(declared), outside_scope_identical=True, changed=changed, state_before=state)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--accepted-input-hashes", type=Path)
    parser.add_argument("--eras", type=Path, default=ROOT / uni.ERAS)
    args = parser.parse_args(argv)
    source, output = args.input_dir.resolve(), args.output_dir.resolve()
    require(source != output, "output directory must differ from the read-only input")
    raw = read(source / NAME)
    require(sha(raw) in accepted_hashes(args.accepted_input_hashes), "unexpected input hash: " + NAME)
    eras = json.loads(read(args.eras))
    new, receipt = transform(raw, eras)
    again, _ = transform(new, eras)
    require(again == new, "native uniform repair is not idempotent")
    receipt.update(schema=SCHEMA, runtime_witnessed=False, idempotent=True, eras_sha256=sha(read(args.eras)),
                   touched_disc_files=[NAME + " (outer 22, PACK0)"])
    output.mkdir(parents=True, exist_ok=True)
    write_new(output / NAME, new)
    write_new(output / "a3_receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    print(json.dumps({"status": "DONE", "output": str(output), "receipt": str(output / "a3_receipt.json"),
                      "bytes_changed": receipt["bytes_changed"], "after_sha256": receipt["after_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
