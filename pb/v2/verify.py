#!/usr/bin/env python3
"""PROVED OFFLINE league verification for the v2 offense (beta 77, job p48o).

For every team: pack check (7 stages, native scoring), compose retail -> v2 offense ->
defense pack -> position pools -> kickoff alignment -> kickoff returns -> depth roles ->
screen timing D (``pb/v2/compose.py``), native menu walk of every formation (retail
instructions under Unicorn, the old pb/verify.py walker), the playbook linter when it
is present (job p13's ``nfl2k5_playbook_lint``), and, against the shipped v0.5 PLAY
entry, decoded equality of everything the offense does not own.  Writes
``pb/v2/receipts/league-offline.json`` and the composed books to ``--books``.
Never starts xemu; gameplay is unwitnessed.
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

V05_SHA256 = "5317a7b16558621e4030f3883789060f37a42af542df431a5d338b2ca1f3c76f"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def defense_owned(defense_pack, composed: bytes):
    """(play indices, formation indices) the v2 defense pack writes (p48d: its repair tool computes the same sets)."""
    if defense_pack is None:
        return set(), set()
    sys.path[:0] = [str(ROOT / "tools" / "b77")]
    from p48d_repair import owned
    from mod_editor.core import nfl2k5_playbook_inspector as insp
    plays, forms, linked = owned(defense_pack, insp.parse_playbook_resource(composed))
    return set(plays), set(forms) | set(linked)


def decoded_outside_offense(retail: bytes, composed: bytes, v05: bytes, defense_pack=None) -> dict:
    """Plays and formations the offense does not own, decoded, composed vs v0.5.  With ``defense_pack`` (the v2
    defense, job p48d) the records that pack writes are excluded: they are expected to differ from v0.5 and are
    counted in ``defense_owned`` instead."""
    owned_plays, owned_forms = defense_owned(defense_pack, composed)
    from mod_editor.core import nfl2k5_playbook_inspector as insp
    from mod_editor.core import nfl2k5_play_library as lib
    from mod_editor.core.nfl2k5_complete_offense import ordinary_indices
    rb = insp.parse_playbook_resource(retail)
    fs, ps = ordinary_indices(rb, retail[32:])
    a, b = insp.parse_playbook_resource(composed), insp.parse_playbook_resource(v05)
    ab, bb = composed[32:], v05[32:]
    plays_diff = [p.index for p in a.plays if p.index not in ps and p.index not in owned_plays and (
        lib.play_chains(ab, p.index) != lib.play_chains(bb, p.index) or p.name != b.plays[p.index].name)]
    forms_diff = []
    for f in a.formations:
        if f.index in fs or f.index in owned_forms:
            continue
        off = insp.FORMATION_BASE + f.index * insp.FORMATION_SIZE
        aux = insp.FORMATION_AUX_BASE + f.index * insp.FORMATION_AUX_SIZE
        if (ab[off + 4:off + insp.FORMATION_SIZE] != bb[off + 4:off + insp.FORMATION_SIZE]
                or ab[aux:aux + 80] != bb[aux:aux + 80] or f.name != b.formations[f.index].name):
            forms_diff.append(f.index)
    cats_diff = []
    for ci in a.categories:
        off = insp.CATEGORY_BASE + ci.index * insp.CATEGORY_SIZE
        if ab[off + 4:off + 16] != bb[off + 4:off + 16]:
            codes = list(ab[off + 5:off + 16])
            cats_diff.append(dict(index=ci.index, name=ci.name.strip(), offense=lib.is_offense_category(codes)))
    return dict(defense_owned=dict(plays=len(owned_plays), formations=len(owned_forms)),
                retained_plays=len(a.plays) - len(ps), plays_differing=plays_diff,
                retained_formations=len(a.formations) - len(fs), formations_differing=forms_diff,
                categories_differing=cats_diff,
                defensive_categories_differing=[c for c in cats_diff if not c["offense"]])


def team_job(job):
    team, retail, v05, xbe, books_dir = job
    from mod_editor.core import nfl2k5_playbook_pack as packs
    from pb.v2 import compose as comp
    from pb.v2.build import pack_path
    from pb.verify import native_receipt
    offense = packs.load_pack(pack_path(team))
    defense = packs.load_pack(ROOT / f"data/playbooks/softdrink_{team.lower()}_defense.2k5book")
    check = packs.check_pack(offense, resource=retail, xbe=xbe)
    if not check.ok:
        return dict(team=team, ok=False, check=check.text()[-2000:])
    final, receipt, a, _b = comp.compose(team, retail, offense, defense, xbe)
    (Path(books_dir) / f"{team}.play").write_bytes(final)
    walks = native_receipt(xbe, final)
    lint = None
    try:
        from mod_editor.core import nfl2k5_playbook_lint as linter
        report = linter.lint_resource(final, team)
        lint = dict(links=report.links_checked, findings=report.counts(),
                    offense_findings=sum(1 for f in report.findings if not f.code.startswith("DEF_")))
    except ImportError:
        pass
    preserved = decoded_outside_offense(retail, final, v05, defense)
    return dict(team=team, ok=True, pack_sha256=sha(pack_path(team).read_bytes()), compose=receipt,
                formations=len(walks), menu_entries=sum(len(w["plays"]) for w in walks),
                unique_plays=len({p for w in walks for p in w["plays"]}),
                pages=sum(len(w["pages"]) for w in walks), walks_ended=all(w["ended"] for w in walks),
                lint=lint, preserved=preserved, v05_entry_sha256=sha(v05))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--image", type=Path, required=True, help="retail ISO")
    ap.add_argument("--v05", type=Path, required=True, help="SOFTDRINK 2K28 v0.5 disc (read only)")
    ap.add_argument("--xbe", type=Path, required=True, help="retail default.xbe")
    ap.add_argument("--books", type=Path, required=True, help="directory for composed <TEAM>.play files")
    ap.add_argument("--team", action="append")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    from mod_editor.core import nfl2k5_playbook_pack as packs
    xbe = args.xbe.read_bytes()
    if sha(xbe) != "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9":
        raise SystemExit("expected the retail USA default.xbe")
    args.books.mkdir(parents=True, exist_ok=True)
    teams = args.team or list(packs.TEAM_BOOKS)
    with OuterImage(args.image) as retail_image, OuterImage(args.v05) as v05_image:
        jobs = [(t, retail_image.read_entry(BOOK_ENTRIES[t]), v05_image.read_entry(BOOK_ENTRIES[t]), xbe, str(args.books))
                for t in teams]
    rows = {}
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(team_job, jobs):
            rows[row["team"]] = row
            print(row["team"], row["ok"], row.get("formations"), row.get("unique_plays"),
                  "lint", (row.get("lint") or {}).get("offense_findings"),
                  "preserved", {k: (len(v) if isinstance(v, list) else v) for k, v in (row.get("preserved") or {}).items()},
                  flush=True)
    out = dict(status="PROVED OFFLINE", runtime_witness=False, generator="pb/v2/build.py",
               scope="retail instructions under Unicorn (scoring, menu walk); no gameplay", teams=rows)
    if not args.team:
        dest = ROOT / "pb" / "v2" / "receipts"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "league-offline.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    bad = [t for t, r in rows.items() if not r["ok"]]
    if bad:
        raise SystemExit(f"failed: {bad}")


if __name__ == "__main__":
    main()
