#!/usr/bin/env python3
"""Native PLAY repair for SOFTDRINK 2K28 v0.5 team books: the v2 offense (beta 77, job p48o).

Owned disc bytes: PACK0 PLAY entries 307..342 for the 32 team books (Editor 318, GEN 320,
PRACTICE 334, reference 335 and WCO 343 are refused).  The SOFTDRINK offense rebuilds a
book's node and name pools, so an entry is rebuilt as a whole, the way the Studio Build
does: retail entry -> v2 offense pack -> defense pack -> position pools -> kickoff
alignment -> kickoff returns -> depth roles -> screen timing D (``pb/v2/compose.py``,
the same code a Build runs).  The v0.5 input entry is hash-checked and used for the
preservation proof: every retained play (defense, kicking, specials), every retained
formation record and menu, and every defensive category decode identically before and
after.  The retail entry is pinned by hash.  Native PLAY scoring runs on both compiles
(retail default.xbe required).  Deterministic; outputs and receipts are created
exclusively; a known output is accepted as input (idempotent).  No gameplay witness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_playbook_inspector as inspector  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402
from pb.v2 import compose  # noqa: E402
from pb.v2.build import pack_path  # noqa: E402
from pb.v2.verify import decoded_outside_offense  # noqa: E402

SCHEMA = "b77.p48o.softdrink-offense-v2.v1"
MANIFEST = Path(__file__).with_name("p48o_repair_manifest.json")
RESOURCE_SIZE = inspector.RESOURCE_HEADER_SIZE + inspector.BODY_SIZE
RETAIL_XBE_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def team_for(entry_id: int) -> str:
    row = manifest()["books"].get(str(entry_id))
    if row is None:
        raise ValueError(f"PACK0 entry {entry_id} is not a SOFTDRINK team book this repair owns")
    return row["team"]


def build(retail: bytes, team: str, xbe: bytes) -> tuple[bytes, dict]:
    offense = packs.load_pack(pack_path(team))
    defense = packs.load_pack(ROOT / f"data/playbooks/softdrink_{team.lower()}_defense.2k5book")
    final, receipt, _a, _b = compose.compose(team, retail, offense, defense, xbe)
    receipt["offense_pack_sha256"] = sha(pack_path(team).read_bytes())
    receipt["defense_pack_sha256"] = sha((ROOT / f"data/playbooks/softdrink_{team.lower()}_defense.2k5book").read_bytes())
    return final, receipt


def repair_resource(payload: bytes, entry_id: int, retail: bytes, xbe: bytes, *,
                    expected_input_sha256: str | None = None) -> tuple[bytes, dict]:
    if len(payload) != RESOURCE_SIZE or len(retail) != RESOURCE_SIZE:
        raise ValueError("Expected fixed-size 0x20 + 0x13390 PLAY resources")
    if sha(xbe) != RETAIL_XBE_SHA256:
        raise ValueError("Native scoring needs the retail USA default.xbe")
    row = manifest()["books"].get(str(entry_id))
    if row is None:
        raise ValueError(f"PACK0 entry {entry_id} is not a SOFTDRINK team book this repair owns")
    if sha(retail) != row["retail_sha256"]:
        raise ValueError(f"{row['team']}: retail entry hash differs from the pinned retail book")
    before = sha(payload)
    accepted = {row["v05_sha256"], row.get("after_sha256")} | set(row.get("stacked_inputs", []))
    if expected_input_sha256:
        accepted.add(expected_input_sha256)
    if before not in accepted:
        raise ValueError(f"{row['team']}: unexpected PLAY input SHA256 {before}")
    result, steps = build(retail, row["team"], xbe)
    if row.get("after_sha256") and sha(result) != row["after_sha256"]:
        raise ValueError(f"{row['team']}: output differs from the manifest (packs changed? regenerate the manifest)")
    defense_pack = packs.load_pack(ROOT / f"data/playbooks/softdrink_{row['team'].lower()}_defense.2k5book")
    # the v2 defense (job p48d) rewrites its own plays/formations; everything else must decode as in v0.5
    preserved = decoded_outside_offense(retail, result, payload, defense_pack)
    if preserved["plays_differing"] or preserved["defensive_categories_differing"]:
        raise ValueError(f"{row['team']}: a retained play or defensive category changed: {preserved}")
    receipt = dict(schema=SCHEMA, disc_file="media/pack0.bin", pack0_entry_id=entry_id, book=row["team"],
                   size=len(payload), before_sha256=before, after_sha256=sha(result), retail_sha256=sha(retail),
                   status="applied" if result != payload else "already_applied",
                   changed_bytes=sum(a != b for a, b in zip(payload, result)),
                   declared_scope=dict(file_offset_in_entry="0x0", size=RESOURCE_SIZE,
                                       label="whole PLAY entry: offense records, menus, node and name pools rebuilt"),
                   preserved_decoded=preserved, compose=steps, runtime_witness=False)
    return result, receipt


def _write_exclusive(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def _read_entry(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{path}: expected a regular extracted PLAY resource")
    with path.open("rb") as stream:
        return stream.read(RESOURCE_SIZE + 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    one = sub.add_parser("entry", help="repair one extracted PACK0 PLAY entry")
    one.add_argument("source", type=Path)
    one.add_argument("output", type=Path)
    one.add_argument("--entry-id", required=True, type=int)
    one.add_argument("--retail-entry", required=True, type=Path, help="the same team's extracted retail PLAY entry")
    one.add_argument("--xbe", required=True, type=Path, help="retail default.xbe (native scoring)")
    one.add_argument("--receipt", required=True, type=Path)
    one.add_argument("--expected-input-sha256")
    man = sub.add_parser("manifest", help="pin v0.5, retail and output hashes for the 32 team entries")
    man.add_argument("--v05", required=True, type=Path)
    man.add_argument("--retail", required=True, type=Path)
    man.add_argument("--xbe", required=True, type=Path)
    allp = sub.add_parser("all", help="repair all 32 team entries read from the discs (read only)")
    allp.add_argument("--v05", required=True, type=Path)
    allp.add_argument("--retail", required=True, type=Path)
    allp.add_argument("--xbe", required=True, type=Path)
    allp.add_argument("--out", required=True, type=Path, help="new directory for <entry>.play and receipts")
    args = ap.parse_args(argv)
    xbe = args.xbe.read_bytes()
    if args.cmd == "entry":
        if args.output.exists() or args.receipt.exists() or args.output.absolute() == args.receipt.absolute():
            ap.error("choose distinct new output and receipt paths")
        try:
            result, receipt = repair_resource(_read_entry(args.source), args.entry_id, _read_entry(args.retail_entry),
                                              xbe, expected_input_sha256=args.expected_input_sha256)
        except ValueError as exc:
            ap.error(str(exc))
        _write_exclusive(args.output, result)
        with args.receipt.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, indent=1)
            stream.write("\n")
        print(json.dumps({k: receipt[k] for k in ("book", "status", "before_sha256", "after_sha256", "changed_bytes")}))
        return
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    if args.cmd == "manifest":
        if sha(xbe) != RETAIL_XBE_SHA256:
            ap.error("native scoring needs the retail USA default.xbe")
        stacked = {}
        # b77 p6s: a regenerated manifest keeps accepting every earlier output of this repair (e.g. the p48o
        # entries) and their own stacked inputs, so the new books apply on top of an already repaired disc
        if MANIFEST.is_file():
            for entry, row in manifest().get("books", {}).items():
                for h in [row.get("after_sha256"), *row.get("stacked_inputs", [])]:
                    if h:
                        stacked.setdefault(str(entry), []).append(h)
        p13 = Path(__file__).with_name("p13_repair_manifest.json")
        if p13.is_file():
            for entry, row in json.loads(p13.read_text(encoding="utf-8")).get("books", {}).items():
                if isinstance(row, dict) and row.get("after_sha256"):
                    stacked.setdefault(str(entry), []).append(row["after_sha256"])
        books = {}
        with OuterImage(args.v05) as v05, OuterImage(args.retail) as retail:
            for team in packs.TEAM_BOOKS:
                entry = BOOK_ENTRIES[team]
                raw, base = v05.read_entry(entry), retail.read_entry(entry)
                result, _receipt = build(base, team, xbe)
                books[str(entry)] = dict(team=team, v05_sha256=sha(raw), retail_sha256=sha(base),
                                         after_sha256=sha(result),
                                         stacked_inputs=sorted(set(stacked.get(str(entry), [])) - {sha(result), sha(raw)}))
                print(team, entry, sha(result)[:16], flush=True)
        MANIFEST.write_text(json.dumps(dict(schema=SCHEMA, v05_disc_sha256=
                                            "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f",
                                            books=books), indent=1) + "\n", encoding="utf-8", newline="\n")
        return
    args.out.mkdir(parents=False, exist_ok=False)
    rows = []
    with OuterImage(args.v05) as v05, OuterImage(args.retail) as retail:
        for key, row in sorted(manifest()["books"].items(), key=lambda kv: int(kv[0])):
            entry = int(key)
            result, receipt = repair_resource(v05.read_entry(entry), entry, retail.read_entry(entry), xbe)
            _write_exclusive(args.out / f"{entry}.play", result)
            (args.out / f"{entry}.receipt.json").write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8",
                                                           newline="\n")
            rows.append({k: receipt[k] for k in ("pack0_entry_id", "book", "before_sha256", "after_sha256", "changed_bytes")})
            print(json.dumps(rows[-1]), flush=True)
    (args.out / "summary.json").write_text(json.dumps(dict(schema=SCHEMA, entries=rows), indent=1) + "\n",
                                           encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
