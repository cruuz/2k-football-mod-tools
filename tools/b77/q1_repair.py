#!/usr/bin/env python3
"""b77 / q1: native repair for the v0.5 disc, every quarterback's Throw Power up a bit (GOAL R1).

Throw Power is the roster record byte +0x38 (pass_arm_strength); see mod_editor/core/nfl2k5_qb_throw_power.py for why
and for the exact rule (new = min(cap, old + add), default +4 and cap 99). This tool changes exactly those bytes and no
others, in the ROST resources of the disc:

  main.ROST                 outer entry 5: the 2026 league, free agents, draft class and the 68 secondary records
                            (the rookie generator's templates, so generated classes follow)
  outer_NNNN.ROST           every one-team ROST file (outer entry NNNN): the Anniversary moments and historic teams;
                            a file may also be named by its game name (h-07-1971-cowboys-4.iff)

  python3 tools/b77/q1_repair.py extract  --disc DISC.iso --out DIR              # the 201 ROST resources, read only
  python3 tools/b77/q1_repair.py baseline --disc DISC.iso --out data/nfl2k5_qb_throw_power_baseline_v05.json
  python3 tools/b77/q1_repair.py repair   --input-dir DIR --output-dir NEW [--add 4] [--cap 99] [--scope all|main]
                                          [--accepted-input-hashes JSON] [--allow-stacked-input]
  python3 tools/b77/q1_repair.py merge-edits --edits LEAGUE_ROSTER_EDITS.json --out NEW.json [--add 4]   # Studio route
  python3 tools/b77/q1_repair.py check    --disc DISC.iso                         # the baseline still matches the disc

Rules the repair enforces:
  * an input must carry the v0.5 hash, or the hash this repair writes (then output = input, idempotent), or a hash named
    in --accepted-input-hashes ({"files": {name: sha256}}), or --allow-stacked-input must be given (another job already
    changed the file; then every QB record is still checked by player identity and by value);
  * a file that holds some QBs raised and others not (a partial earlier run) is refused;
  * only files whose bytes change are written; a different existing output is never replaced;
  * every byte outside the declared QB Throw Power bytes is proved identical, and a second run changes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_qb_throw_power as qp  # noqa: E402
from mod_editor.core import nfl2k5_roster_records as rr  # noqa: E402

SCHEMA = "b77/q1_native_repair/v1"
BASELINE_SCHEMA = "b77/q1_baseline/v1"
BASELINE_PATH = ROOT / "data" / "nfl2k5_qb_throw_power_baseline_v05.json"
MAIN_NAME = "main.ROST"
OUTER_NAME = re.compile(r"outer_(\d{4,6})\.ROST")
MAX_RESOURCE = 8 * 1024 * 1024
V05_DISC_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"


class RepairError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise RepairError(message)


def read_file(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "rb") as handle:
        return handle.read(MAX_RESOURCE + 1)


def write_new(path, raw):
    """New files only: an identical existing file is accepted (replay), a different one is never replaced."""
    path = Path(path)
    if path.exists():
        require(read_file(path) == raw, f"refusing to replace different output: {path}")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o644)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def resource_name(outer_index):
    return MAIN_NAME if outer_index == qp.MAIN_OUTER_INDEX else f"outer_{outer_index:04d}.ROST"


# ------------------------------------------------------------------------------------------------ disc side
def rost_resources(disc):
    """[(outer index, name_id, raw)] for every ROST resource of the disc image (read only)."""
    out = []
    with rr._outer_image()(disc) as image:
        for entry in image.entries:
            if entry.size <= qp.WRAPPER + 0x100:
                continue
            raw = image.read_entry(entry.index)
            if qp.is_rost(raw):
                out.append((entry.index, entry.name_id, raw))
    return out


def build_baseline(disc, add=qp.DEFAULT_ADD, cap=qp.DEFAULT_CAP):
    files = []
    for index, name_id, raw in rost_resources(disc):
        try:
            rows = qp.quarterbacks(raw)
        except (rr.RosterRecordError, qp.QbThrowPowerError) as exc:
            files.append(dict(outer_index=index, name_id=name_id, size=len(raw), sha256=qp.sha256(raw), unreadable=str(exc)))
            continue
        after, changes = qp.apply_resource(raw, add, cap)
        files.append(dict(
            outer_index=index, name_id=name_id, name=resource_name(index), size=len(raw), sha256=qp.sha256(raw),
            sha256_after=qp.sha256(after), qb_count=len(rows), bytes_changed=len(changes),
            quarterbacks=[dict(pool=r["pool"], index=r["index"], first=r["first"], last=r["last"], group=r["group"],
                               offset=r["offset"], value=r["value"]) for r in rows]))
    return dict(schema=BASELINE_SCHEMA, disc_sha256=V05_DISC_SHA256, add=add, cap=cap, files=files)


def load_baseline(path=BASELINE_PATH):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    require(doc.get("schema") == BASELINE_SCHEMA, "not a q1 baseline")
    return doc


# ------------------------------------------------------------------------------------------------ the repair
def classify(rows, base_rows, add, cap):
    """Per QB row: before | applied | foreign | new, against the v0.5 baseline rows of the same file."""
    known = {(b["pool"], b["index"], b["first"], b["last"]): b for b in base_rows}
    states = []
    for row in rows:
        b = known.get((row["pool"], row["index"], row["first"], row["last"]))
        if b is None:
            states.append("new")
        elif row["value"] == b["value"]:
            states.append("before")
        elif row["value"] == qp.raised(b["value"], add, cap):
            states.append("applied")
        else:
            states.append("foreign")
    return states


def repair_resource(raw, entry, add, cap, accepted, allow_stacked, name):
    """(new bytes, per-file receipt) for one ROST resource; refuses what it cannot prove."""
    digest = qp.sha256(raw)
    known = {entry["sha256"], entry["sha256_after"]} | set(accepted.get(name, ()))
    stacked = digest not in known
    require(not stacked or allow_stacked, f"{name}: unexpected input hash {digest[:16]} (not v0.5, not this repair's output)")
    rows = qp.quarterbacks(raw)
    states = classify(rows, entry["quarterbacks"], add, cap)
    # a row the rule would not change reads the same before and after; only the changing rows say which state it is
    moving = [(r, s) for r, s in zip(rows, states) if qp.raised(r["value"], add, cap) != r["value"] or s == "applied"]
    applied = [r for r, s in moving if s == "applied"]
    fresh = [r for r, s in moving if s != "applied"]
    require(not (applied and fresh), f"{name}: partly applied already ({len(applied)} raised, {len(fresh)} not)")
    out, changes = qp.apply_resource(raw, add, cap) if not applied else (raw, [])
    diff = [i for i in range(len(raw)) if raw[i] != out[i]]
    require(diff == sorted(c["offset"] for c in changes), f"{name}: the write changed bytes beyond the QB Throw Power bytes")
    return out, dict(
        name=name, outer_index=entry["outer_index"], size=len(raw), before_sha256=digest, after_sha256=qp.sha256(out),
        stacked_input=stacked, qb_records=len(rows), bytes_changed=len(diff), outside_scope_identical=True,
        already_applied=bool(applied), states={s: states.count(s) for s in sorted(set(states))},
        changed=[dict(pool=c["pool"], index=c["index"], name=f"{c['first']} {c['last']}", group=c["group"],
                      byte_offset=c["offset"], before=c["before"], after=c["after"]) for c in changes])


def map_input_files(input_dir, baseline):
    """{outer index: path} for the ROST files found in `input_dir` (main.ROST, outer_NNNN.ROST or a game file name)."""
    from mod_editor.core import nfl2k5_espn25_more_moments as mm
    by_id = {f["name_id"]: f["outer_index"] for f in baseline["files"]}
    found = {}
    for path in sorted(Path(input_dir).iterdir()):
        if not path.is_file():
            continue
        match = OUTER_NAME.fullmatch(path.name)
        if path.name == MAIN_NAME:
            index = qp.MAIN_OUTER_INDEX
        elif match:
            index = int(match.group(1))
        elif path.name.endswith(".iff") and mm.name_id(path.name) in by_id:
            index = by_id[mm.name_id(path.name)]
        else:
            continue
        require(index not in found, f"two input files for outer entry {index}")
        found[index] = path
    return found


def accepted_hashes(path):
    out = {}
    if path is not None:
        manifest = json.loads(read_file(path))
        files = manifest.get("files", manifest)
        require(isinstance(files, dict), "accepted input manifest must be an object")
        for name, row in files.items():
            if isinstance(row, dict):
                row = row.get("sha256") or row.get("after_sha256")
            require(isinstance(row, str) and re.fullmatch(r"[0-9a-f]{64}", row), f"{name}: invalid accepted sha256")
            out.setdefault(name, set()).add(row)
    return out


def native_repair(input_dir, output_dir, *, add=qp.DEFAULT_ADD, cap=qp.DEFAULT_CAP, scope="all", accepted=None,
                  allow_stacked=False, baseline=None):
    input_dir, output_dir = Path(input_dir).resolve(), Path(output_dir).resolve()
    require(input_dir != output_dir, "output directory must differ from the read-only input")
    plan = qp.normalise_directive(dict(add=add, cap=cap, scope=scope))
    baseline = baseline or load_baseline()
    entries = {f["outer_index"]: f for f in baseline["files"] if "quarterbacks" in f}
    found = map_input_files(input_dir, baseline)
    require(found, f"no ROST resources found in {input_dir}")
    wanted = [i for i in sorted(entries) if plan["scope"] == "all" or i == qp.MAIN_OUTER_INDEX]
    results, files = {}, {}
    for index in wanted:
        if index not in found:
            continue
        name = resource_name(index)
        raw = read_file(found[index])
        new, receipt = repair_resource(raw, entries[index], plan["add"], plan["cap"], accepted or {}, allow_stacked, name)
        receipt["input_file"] = found[index].name
        files[name] = receipt
        if new != raw:
            results[name] = new
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, raw in results.items():
        write_new(output_dir / name, raw)
    receipt = dict(
        schema=SCHEMA, runtime_witnessed=False, directive=plan, rule="new = min(cap, old + add), never below old; "
        "QB records only (position code 0); one byte per record at record offset +0x38",
        byte_in_record=qp.BYTE_IN_RECORD, resources_present=len(files),
        resources_missing=[resource_name(i) for i in wanted if i not in found],
        resources_written=sorted(results), bytes_changed=sum(f["bytes_changed"] for f in files.values()),
        outside_scope_identical=True, files=files)
    write_new(output_dir / "q1_receipt.json", (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    return receipt


# ------------------------------------------------------------------------------------------------ cli
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "baseline", "check"):
        p = sub.add_parser(name)
        p.add_argument("--disc", required=True, type=Path)
        if name != "check":
            p.add_argument("--out", required=True, type=Path)
    m = sub.add_parser("merge-edits", help="add the qb_throw_power directive to the league project's roster edits")
    m.add_argument("--edits", required=True, type=Path)
    m.add_argument("--out", required=True, type=Path)
    m.add_argument("--add", type=int, default=qp.DEFAULT_ADD)
    m.add_argument("--cap", type=int, default=qp.DEFAULT_CAP)
    m.add_argument("--scope", default="all", choices=qp.SCOPES)
    r = sub.add_parser("repair")
    r.add_argument("--input-dir", required=True, type=Path)
    r.add_argument("--output-dir", required=True, type=Path)
    r.add_argument("--add", type=int, default=qp.DEFAULT_ADD)
    r.add_argument("--cap", type=int, default=qp.DEFAULT_CAP)
    r.add_argument("--scope", default="all", choices=qp.SCOPES)
    r.add_argument("--accepted-input-hashes", type=Path)
    r.add_argument("--allow-stacked-input", action="store_true")
    r.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    args = parser.parse_args(argv)
    if args.command == "extract":
        args.out.mkdir(parents=True, exist_ok=True)
        count = 0
        for index, _name_id, raw in rost_resources(args.disc):
            write_new(args.out / resource_name(index), raw)
            count += 1
        print(json.dumps({"out": str(args.out), "resources": count}))
    elif args.command == "baseline":
        doc = build_baseline(args.disc)
        args.out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"out": str(args.out), "files": len(doc["files"]),
                          "quarterbacks": sum(f.get("qb_count", 0) for f in doc["files"])}))
    elif args.command == "merge-edits":
        merged = qp.merge_into_edits(json.loads(read_file(args.edits)), dict(add=args.add, cap=args.cap, scope=args.scope))
        write_new(args.out, (json.dumps(merged, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
        print(json.dumps({"out": str(args.out), "qb_throw_power": merged[qp.DIRECTIVE_KEY]}))
    elif args.command == "check":
        fresh, saved = build_baseline(args.disc), load_baseline()
        same = fresh == saved
        print(json.dumps({"baseline_matches_disc": same}))
        return 0 if same else 1
    else:
        receipt = native_repair(args.input_dir, args.output_dir, add=args.add, cap=args.cap, scope=args.scope,
                                accepted=accepted_hashes(args.accepted_input_hashes),
                                allow_stacked=args.allow_stacked_input, baseline=load_baseline(args.baseline))
        print(json.dumps({"resources_present": receipt["resources_present"], "resources_missing": receipt["resources_missing"],
                          "resources_written": len(receipt["resources_written"]), "bytes_changed": receipt["bytes_changed"],
                          "receipt": str(args.output_dir / "q1_receipt.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
