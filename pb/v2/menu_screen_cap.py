#!/usr/bin/env python3
"""Hold every offense menu to at most two screens (job pb2's menu rule) in the shipped packs (b777 pb4).

The v4 generator's last volume pass added shared plays a page (three) at a time and scored the three against the
same menu, so five menus took a third screen.  This drops the extra screens from the end of the menu, then shared
non-screen links from the end until the menu is a multiple of three again.  Only links whose play stays listed in
another menu are dropped (no record loses its last link) and the first page (the formation's featured plays) is
kept.  Packs, catalogs and both manifests are updated; the generator itself no longer does this (fixed in
``build_book``).

    python3 pb/v2/menu_screen_cap.py [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_playbook_pack as packs  # noqa: E402

MAX_SCREENS = 2


def is_screen(name: str) -> bool:
    return "screen" in name.lower()


def fix_doc(doc: dict) -> list:
    names = {p["id"]: p["custom_name"] for p in doc["plays"]}
    uses = Counter(pid for menu in doc["menus"].values() for pid in menu)
    changes = []
    for fid, menu in doc["menus"].items():
        screens = [pid for pid in menu if is_screen(names[pid])]
        if len(screens) <= MAX_SCREENS:
            continue
        drop = []
        for pid in reversed(menu[3:]):
            if len([p for p in screens if p not in drop]) <= MAX_SCREENS:
                break
            if is_screen(names[pid]) and uses[pid] > 1:
                drop.append(pid)
        for pid in reversed(menu[3:]):
            if (len(menu) - len(drop)) % 3 == 0:
                break
            if pid not in drop and not is_screen(names[pid]) and uses[pid] > 1:
                drop.append(pid)
        if len([p for p in screens if p not in drop]) > MAX_SCREENS or (len(menu) - len(drop)) % 3:
            raise SystemExit(f"{doc['book']['team']} {fid}: cannot cap the screens safely")
        for pid in drop:
            uses[pid] -= 1
        doc["menus"][fid] = [pid for pid in menu if pid not in drop]
        changes.append(dict(formation=fid, dropped=[names[p] for p in drop], links=len(doc["menus"][fid])))
    return changes


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    from pb.v2 import generator as gen
    manifest = json.loads((ROOT / "pb/v2/manifest.json").read_text())
    total = 0
    for row in manifest["teams"]:
        path = ROOT / row["pack"]
        doc = json.loads(path.read_text(encoding="utf-8"))
        changes = fix_doc(doc)
        total += len(changes)
        if not changes:
            continue
        print(row["team"], changes)
        if args.check:
            continue
        pack = packs.loads_pack(json.dumps(doc))
        packs.save_pack(pack, path)
        catp = ROOT / "pb/v2/catalogs" / f"{row['team']}.json"
        cat = json.loads(catp.read_text())
        fname = {f["id"]: f.get("custom_name") or f.get("replace_name") for f in doc["formations"]}
        names = {p["id"]: p["custom_name"] for p in doc["plays"]}
        rows = {f["formation"]: f for f in cat["formations"]}
        for fid, menu in doc["menus"].items():
            if fname.get(fid) in rows:
                rows[fname[fid]]["menu"] = [names[p] for p in menu]
        catp.write_text(json.dumps(cat, indent=1) + "\n", encoding="utf-8", newline="\n")
        row["links"] = sum(len(m) for _f, m in pack.menus)
        row["semantic_sha256"] = gen.semantic_digest(packs.loads_pack(pack.dumps()))
    if not args.check and total:
        (ROOT / "pb/v2/manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
        league = json.loads((ROOT / "pb/league_manifest.json").read_text())
        by = {r["team"]: r for r in manifest["teams"]}
        for r in league["teams"]:
            r["semantic_sha256"] = by[r["team"]]["semantic_sha256"]
        (ROOT / "pb/league_manifest.json").write_text(json.dumps(league, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("menus over the screen cap:", total)
    return 1 if args.check and total else 0


if __name__ == "__main__":
    raise SystemExit(main())
