#!/usr/bin/env python3
"""PROVED OFFLINE league verification for the b776 (pb1) offense books.

For every team, from the retail book and the SHIPPED packs in data/playbooks (offense v3, the re-seated defense):
pack check (7 stages, native scoring), the Build tail (``pb/v2/compose.py``: offense, defense, position pools,
kickoff alignment and returns, depth roles, screen timing D with the shipped pins), the playbook linter, the native
menu walk of every formation (retail instructions under Unicorn), the native PLAY scoring gate, the automatic coach
profile build (``nfl2k5_coach_ai.build_profile``: its tail tag and index bounds), name pool / node / record counts,
and the menu page rule (every offense formation lists a multiple of three plays).  Writes the composed books to
``--books`` and ``pb/v2/receipts/league-offline-v3.json``.  Never starts an emulator; gameplay is unwitnessed.

    python3 pb/v2/verify3.py --image RETAIL.iso --xbe default.xbe --books /tmp/v3books [--team KC] [--workers 4]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

ALIAS = {"ARZ": "ARI", "STL": "LAR", "SD": "LAC", "OAK": "LV"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def team_job(job):
    team, retail, xbe, books_dir = job
    from mod_editor.core import nfl2k5_playbook_pack as packs
    from mod_editor.core import nfl2k5_playbook_inspector as insp
    from mod_editor.core import nfl2k5_playbook_lint as linter
    from mod_editor.core import nfl2k5_coach_ai as coach
    from mod_editor.core.nfl2k5_play_scoring import require_safe
    from mod_editor.core.nfl2k5_complete_offense import ordinary_indices
    from pb.v2 import compose as comp
    from pb.v2.build import pack_path
    from pb.verify import native_receipt
    offense = packs.load_pack(pack_path(team))
    defense = packs.load_pack(ROOT / f"data/playbooks/softdrink_{team.lower()}_defense.2k5book")
    check = packs.check_pack(offense, resource=retail, xbe=xbe)
    if not check.ok:
        return dict(team=team, ok=False, stage="offense check", detail=check.text()[-2000:])
    try:
        final, receipt, a, _b = comp.compose(team, retail, offense, defense, xbe)
    except Exception as exc:  # noqa: BLE001
        return dict(team=team, ok=False, stage="compose", detail=str(exc)[:2000])
    (Path(books_dir) / f"{team}.play").write_bytes(final)
    report = linter.lint_resource(final, team)
    offense_findings = [f.to_json() for f in report.findings if not f.code.startswith("DEF_")]
    walks = native_receipt(xbe, final)
    scoring = require_safe(final, xbe)
    value = json.loads((ROOT / "data/vip/coaches" / f"{ALIAS.get(team, team)}.json").read_text(encoding="utf-8"))
    try:
        _res, coach_receipt = coach.build_profile(final, value)
        coach_ok = dict(ok=True, pools=len(coach_receipt["pools"]),
                        max_play_index=max(c["play"] for p in coach_receipt["pools"] for c in p["choices"]))
    except Exception as exc:  # noqa: BLE001
        coach_ok = dict(ok=False, error=str(exc))
    book = insp.parse_playbook_resource(final)
    rb = insp.parse_playbook_resource(retail)
    fs, ps = ordinary_indices(rb, retail[32:])
    offense_forms = [f for f in book.formations if (f.index in fs or f.index >= len(rb.formations))
                     and (struct.unpack_from("<I", final, 32 + insp.FORMATION_BASE + f.index * insp.FORMATION_SIZE + 4)[0] >> 8) & 0x3F < 4]
    short_pages = [f.name for f in offense_forms if len(f.play_links) % 3]
    dup_links = [f.name for f in book.formations if len({l.play_index for l in f.play_links}) != len(f.play_links)]
    pool_units = struct.unpack_from("<I", final, 32 + 0x1083C)[0]
    ok = (not offense_findings and all(w["ended"] for w in walks) and scoring.get("fault_count") == 0
          and coach_ok["ok"] and not short_pages and not dup_links
          and insp.STRING_BASE + 2 * pool_units <= 0x13000)
    return dict(team=team, ok=ok, offense_pack_sha256=sha(pack_path(team).read_bytes()), compose=receipt,
                lint=report.counts(), offense_findings=offense_findings[:20],
                formations=len(walks), menu_entries=sum(len(w["plays"]) for w in walks),
                walks_ended=all(w["ended"] for w in walks), scoring=dict(status=scoring.get("status"),
                                                                       faults=scoring.get("fault_count")),
                coach_ai=coach_ok, short_page_formations=short_pages, duplicate_link_formations=dup_links,
                counts=dict(formations=len(book.formations), plays=len(book.plays), categories=len(book.categories),
                            nodes=book.node_count, name_pool_units=pool_units,
                            strings_end=hex(insp.STRING_BASE + 2 * pool_units)),
                final_sha256=sha(final))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--xbe", type=Path, required=True)
    ap.add_argument("--books", type=Path, required=True)
    ap.add_argument("--team", action="append")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    from mod_editor.core import nfl2k5_playbook_pack as packs
    xbe = args.xbe.read_bytes()
    args.books.mkdir(parents=True, exist_ok=True)
    teams = args.team or list(packs.TEAM_BOOKS)
    with OuterImage(args.image) as image:
        jobs = [(t, image.read_entry(BOOK_ENTRIES[t]), xbe, str(args.books)) for t in teams]
    rows = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(team_job, jobs):
            rows[row["team"]] = row
            print(row["team"], "OK" if row["ok"] else "FAIL", row.get("stage", ""), row.get("counts"),
                  "lint", row.get("lint"), "coach", row.get("coach_ai"), "short", row.get("short_page_formations"),
                  str(row.get("detail", ""))[:300], flush=True)
    out = dict(status="PROVED OFFLINE", runtime_witness=False, generator="pb/v2/generator.py (b776 pb1)",
               scope="retail instructions under Unicorn (scoring, menu walk); no gameplay", teams=rows)
    if not args.team:
        dest = ROOT / "pb" / "v2" / "receipts"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "league-offline-v3.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    bad = [t for t, r in rows.items() if not r["ok"]]
    if bad:
        raise SystemExit(f"failed: {bad}")


if __name__ == "__main__":
    main()
