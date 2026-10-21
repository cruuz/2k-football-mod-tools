#!/usr/bin/env python3
"""Goal Line Sneak spacing + Tush Push lanes, and RB play names, on the shipped offense packs (b777 tp1).

Noah 10/20: "the tush push causes the game to lag like crazy ... one frame or 2 every 10 sec before it ended".
The v4 Goal Line Sneak set stood the fullback and halfback 1.3 yd from the QB and 1.4 yd apart (retail never puts a
back closer than 2.7 yd to the QB or 2.1 yd to another back), and the Tush Push sent every pusher to the QB's own x,
two of them to the same point.  The generator now aligns the set at retail spacing and drives each pusher straight
up his own lane (``nfl2k5_offense_modern``); this tool applies the same change to the packs generated before it, so
the shipped books do not need a full regeneration:

* the three Goal Line Sneak backs move to the generator's new spots (matched by their old spots, any slot order);
* every Tush Push play is rebuilt with ``om.tush_push`` on the new formation (its line, QB and outside receivers'
  chains are unchanged; the tool checks that);
* play names say RB where they said HB (Noah 10/20: "rename halfback to running back (RB) everywhere"); the
  ``concept`` field keeps the catalog name.

    python3 pb/v2/tush_push_spacing.py --check          # 0 when every pack is already fixed
    python3 pb/v2/tush_push_spacing.py --apply          # rewrite data/playbooks in place

A changed offense changes the book bytes: regenerate the defense packs and screen pins after it, as for
``repair_reversals.py``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402

FORMATION = "Goal Line Sneak"
#: b776 spots of the three backs (TE3, FB, HB) in centimetres -> the generator's spots now
OLD_BACKS = ((0, -384), (73, -274), (-73, -274))
rb_name = om.rb_name


def new_backs() -> tuple:
    spec = oc.FORMATIONS[FORMATION]
    return tuple(spec.positions_cm()[8:])


def _ctx(f: dict) -> oc.FormationContext:
    return oc.FormationContext.build([(float(x), float(z)) for x, z in f["slot_positions"]], f["position_codes"])


def _chains(design) -> list:
    return [[[op, [round(v, 4) if isinstance(v, float) else v for v in vals]] for op, vals in (ch or [])]
            for ch in design.chains]


def _norm(chain) -> list:
    return [[int(op), [round(float(v), 3) for v in vals]] for op, vals in chain]


def fix_doc(doc: dict) -> Counter:
    stats: Counter = Counter()
    moved = dict(zip(OLD_BACKS, new_backs()))
    by_id = {p["id"]: p for p in doc["plays"]}
    for f in doc["formations"]:
        if f["custom_name"] != FORMATION:
            continue
        pos = [tuple(p) for p in f["slot_positions"]]
        if any(p in moved for p in pos):
            f["slot_positions"] = [list(moved.get(p, p)) for p in pos]
            stats["formations_moved"] += 1
        ctx = _ctx(f)
        for pid in doc["menus"][f["id"]]:
            play = by_id[pid]
            if play.get("concept") != "Tush Push":
                continue
            design = om.tush_push(ctx)
            new = _chains(design)
            pushers = {s for s, ch in enumerate(design.chains)
                       if ch and any(n[0] == 0x11 and n[1][0] == 3 and n[1][7] == 1 for n in ch)
                       and ctx.player(s).kind in (oc.HB, oc.FB, oc.TE) and not ctx.player(s).on_los}
            for s in range(11):
                if s not in pushers and _norm(new[s]) != _norm(play["assignments"][s]):
                    raise SystemExit(f"{doc['book']}: {pid} slot {s} would change outside the push stack")
            if any(_norm(new[s]) != _norm(play["assignments"][s]) for s in pushers):
                for s in pushers:
                    play["assignments"][s] = new[s]
                stats["tush_rebuilt"] += 1
    for play in doc["plays"]:
        name = play.get("custom_name") or ""
        if rb_name(name) != name:
            play["custom_name"] = rb_name(name)
            stats["renamed"] += 1
    return stats


def books(folder: Path):
    return sorted(folder.glob("softdrink_*_modern.2k5book"))


def fix_catalog(cat: dict) -> int:
    """The team catalog keeps play names (rows and formation menus): same spelling as the pack."""
    n = 0
    for row in cat.get("plays", []):
        if rb_name(row.get("name") or "") != (row.get("name") or ""):
            row["name"] = rb_name(row["name"]); n += 1
    for row in cat.get("formations", []):
        menu = row.get("menu") or []
        new = [rb_name(m) for m in menu]
        if new != menu:
            row["menu"] = new; n += 1
    return n


def refresh_manifests(teams: set) -> None:
    """Semantic digests in pb/v2/manifest.json and pb/league_manifest.json, as menu_screen_cap does."""
    from pb.v2 import generator as gen
    mpath = ROOT / "pb/v2/manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    for row in manifest["teams"]:
        if row["team"] in teams:
            pack = packs.load_pack(ROOT / row["pack"])
            row["semantic_sha256"] = gen.semantic_digest(packs.loads_pack(pack.dumps()))
    mpath.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    lpath = ROOT / "pb/league_manifest.json"
    league = json.loads(lpath.read_text(encoding="utf-8"))
    by = {r["team"]: r for r in manifest["teams"]}
    for r in league["teams"]:
        r["semantic_sha256"] = by[r["team"]]["semantic_sha256"]
    lpath.write_text(json.dumps(league, indent=2) + "\n", encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packs", type=Path, default=ROOT / "data/playbooks")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    total: Counter = Counter()
    manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text(encoding="utf-8"))
    team_of = {Path(r["pack"]).name: r["team"] for r in manifest["teams"]}
    changed = set()
    for path in books(a.packs):
        doc = json.loads(path.read_text(encoding="utf-8"))
        stats = fix_doc(doc)
        team = team_of.get(path.name)
        catp = ROOT / "pb/v2/catalogs" / f"{team}.json"
        if team and a.packs == ROOT / "data/playbooks" and catp.is_file():
            cat = json.loads(catp.read_text(encoding="utf-8"))
            if fix_catalog(cat):
                stats["catalog_rows"] += 1
                if a.apply:
                    catp.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8", newline="\n")
        if a.apply and stats:
            packs.save_pack(packs.pack_from_json(doc), path)
            changed.add(team)
        print(path.name, dict(stats))
        total.update(stats)
    if a.apply and changed and a.packs == ROOT / "data/playbooks":
        refresh_manifests(changed)
    if not a.apply and a.packs == ROOT / "data/playbooks":
        from pb.v2 import generator as gen
        for row in manifest["teams"]:
            pack = packs.load_pack(ROOT / row["pack"])
            if row["semantic_sha256"] != gen.semantic_digest(packs.loads_pack(pack.dumps())):
                total["stale_manifest_rows"] += 1
    print("TOTAL", dict(total))
    return 1 if (a.check and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
