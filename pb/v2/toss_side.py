#!/usr/bin/env python3
"""Shotgun tosses go to the back's own side, on the shipped offense packs (b780 b6-plays).

SWeaR 11/01: "The Crack toss play (under Gun Spread) needs to be tweaked. You always get this janky animation where your
player starts to go outside then cuts immediately back into the middle."  The generator tossed to the formation's
strong side whatever side the back stood on.  In a shotgun set with the back 2.5 yd beside the QB that sent him 8.3 yd
across behind the QB to the lane while the QB pitched: 72 of the 363 toss links in the 32 books did it, and retail does
it once in 83 shotgun tosses (its backs cross behind the QB only from under-centre split-back sets).  The generator now
refuses that side (``nfl2k5_offense_modern.toss_own_side``); this tool applies the same change to the packs generated
before it, so the shipped books do not need a full regeneration:

* every toss link whose QB, linemen and carrier match the generator's toss template (the same recognition the Studio
  compiler runs, ``nfl2k5_playbook_lint.fix_toss_side``) is rebuilt for the back's own side, receivers included;
* the play name follows the side ("Crack Toss" becomes "Crack Toss Wk" when the back's side is the formation's weak
  side); the team catalog keeps the name, the run lane (HOLE_LANES of the new hole) and the formation menus.

    python3 pb/v2/toss_side.py --check          # 0 when every pack is already fixed
    python3 pb/v2/toss_side.py --apply          # rewrite data/playbooks in place, then refresh the manifests

A changed offense changes the book bytes: regenerate the defense packs and screen pins after it
(``python3 pb/v2/defense/regen.py``), as for ``tush_push_spacing.py`` and ``repair_reversals.py``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402
from mod_editor.core import nfl2k5_playbook_lint as lint  # noqa: E402
from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402

HOLE_LANES = (2, 4, 3, 3, 2, 2, 1, 1, 0)              # nfl2k5_vip.HOLE_LANES: native run lane of each take-handoff hole


def _authored(chains) -> list:
    return [[(int(op), list(vals)) for op, vals in chain] for chain in chains]


def _json_chains(chains) -> list:
    return [[[int(op), [round(float(v), 4) if isinstance(v, float) else v for v in vals]] for op, vals in chain]
            for chain in chains]


def _norm(chain) -> list:
    return [[int(op), [round(float(v), 3) for v in vals]] for op, vals in chain]


def new_name(old: str) -> str:
    """The generator's spelling for the turned toss: its side flips, so the " Wk" (weak side) suffix toggles."""
    return old[:-3] if old.endswith(" Wk") else om.rb_name(old + " Wk")[:40]


def fix_doc(doc: dict, homes: dict) -> tuple[Counter, dict]:
    """Rebuild every crossing gun toss of one pack document in place.

    ``homes`` maps a play id to the name of the formation the generator authored it in (the team catalog's ``home``): a
    play linked to several formations carries the receiver blocks the generator gave it there, so the rebuilt play is
    authored in the same formation (all 147 shipped toss plays whose home formation is in the book match it byte for
    byte) and every other formation is checked to need the same quarterback, line and carrier.
    Returns (stats, {play id: (old name, new name, old lane, new lane, names of the formations that carry the play)})."""
    stats: Counter = Counter()
    changed: dict = {}
    by_id = {p["id"]: p for p in doc["plays"]}
    forms = {f["id"]: f for f in doc["formations"]}
    by_name = {f["custom_name"]: f for f in doc["formations"]}
    links: dict = {}
    for fid, menu in doc["menus"].items():
        for pid in menu:
            links.setdefault(pid, []).append(fid)
    for pid, fids in links.items():
        play = by_id[pid]
        chains = _authored(play["assignments"])
        hits = {}
        for fid in fids:
            f = forms[fid]
            fixed, receipt = lint.fix_toss_side(f["slot_positions"], f["position_codes"], chains)
            if fixed is not None:
                hits[fid] = (fixed, receipt)
        if not hits:
            continue
        if len(hits) != len(fids):
            raise SystemExit(f"{doc['book']['team']}: {pid} needs a turn in some formations only ({sorted(hits)} of {fids})")
        home = by_name.get(homes.get(pid))
        hid = home["id"] if home is not None and home["id"] in hits else fids[0]
        f = forms[hid]
        receipt = hits[hid][1]
        ctx = oc.FormationContext.build([(float(x), float(z)) for x, z in f["slot_positions"]], f["position_codes"])
        label = next(lab for lab in ("B", "B2") if ctx.slot(lab) == receipt["carrier"])
        design = om.run_design(ctx, receipt["scheme"], direction=receipt["new_side"], carrier=label, codes=f["position_codes"])
        oc.fill_unassigned(ctx, design)
        new = [_norm(c) for c in _json_chains(design.chains)]
        core = (0, 1, 2, 3, 4, 5, receipt["carrier"])
        for other, (core_only, _r) in hits.items():
            mine = [_norm(c) for c in _json_chains(core_only)]
            if [mine[s] for s in core] != [new[s] for s in core]:
                raise SystemExit(f"{doc['book']['team']}: {pid} would need different tosses in {hid} and {other}")
        old_lane = next(HOLE_LANES[int(n[1][2])] for ch in play["assignments"] for n in ch if n[0] == 0x16)
        play["assignments"] = _json_chains(design.chains)
        old_name = play["custom_name"]
        play["custom_name"] = new_name(old_name)
        new_lane = next(HOLE_LANES[int(n[1][2])] for ch in play["assignments"] for n in ch if n[0] == 0x16)
        changed[pid] = (old_name, play["custom_name"], old_lane, new_lane, [forms[x]["custom_name"] for x in fids])
        stats["tosses_rebuilt"] += 1
        stats["links"] += len(fids)
    return stats, changed


def books(folder: Path):
    return sorted(folder.glob("softdrink_*_modern.2k5book"))


def fix_catalog(cat: dict, changed: dict) -> int:
    """The team catalog keeps play names (rows and formation menus) and the run lane of the handoff hole."""
    n = 0
    renames = {}
    for row in cat.get("plays", []):
        hit = changed.get(row.get("play"))
        if hit:
            old, new, _old_lane, new_lane, formations = hit
            row["name"], row["lane"] = new, new_lane
            for name in formations:
                renames[(name, old)] = new
            n += 1
    for row in cat.get("formations", []):
        menu = row.get("menu") or []
        new_menu = [renames.get((row.get("formation"), m), m) for m in menu]
        if new_menu != menu:
            row["menu"] = new_menu
            n += 1
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--packs", type=Path, default=ROOT / "data/playbooks")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    from pb.v2 import tush_push_spacing as tp
    total: Counter = Counter()
    manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text(encoding="utf-8"))
    team_of = {Path(r["pack"]).name: r["team"] for r in manifest["teams"]}
    touched = set()
    for path in books(a.packs):
        doc = json.loads(path.read_text(encoding="utf-8"))
        team = team_of.get(path.name)
        catp = ROOT / "pb/v2/catalogs" / f"{team}.json"
        homes = {}
        if catp.is_file():
            homes = {r["play"]: r["home"] for r in json.loads(catp.read_text(encoding="utf-8")).get("plays", [])}
        stats, changed = fix_doc(doc, homes)
        if stats and a.apply:
            packs.save_pack(packs.pack_from_json(doc), path)
            touched.add(team)
            if a.packs == ROOT / "data/playbooks" and catp.is_file():
                cat = json.loads(catp.read_text(encoding="utf-8"))
                if fix_catalog(cat, changed):
                    catp.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(path.name, dict(stats))
        total.update(stats)
    if a.apply and touched and a.packs == ROOT / "data/playbooks":
        tp.refresh_manifests(touched)
    print("TOTAL", dict(total))
    return 1 if (a.check and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
