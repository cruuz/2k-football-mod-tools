#!/usr/bin/env python3
"""Playbook variety metrics over PLAY resources (beta 77, job p48o). Read only.

Usage: metrics.py LABEL DIR [LABEL DIR ...] --out metrics.json
Each DIR holds <TEAM>.play resources (0x20 + 0x13390).  Measured on ordinary offensive
plays (family 0, no special flag) the way job u-pb measured v0.5: receiver route chains
(0x12 chains of WR/TE/HB/FB slots, screen blocks excluded), their distinct (type, feet)
segments, play shapes, concepts (names without a leading number), menus, header classes,
formation situation ratings and personnel ids.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402
from mod_editor.core.nfl2k5_complete_offense import ordinary_indices  # noqa: E402

TEAMS = ("ARZ", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX",
         "KC", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "OAK", "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEN", "WAS")
RECEIVERS = {lib.WR, lib.TE, lib.HB, lib.FB}


def concept_name(name: str) -> str:
    return re.sub(r"^\d+\s+", "", name.strip())


def book_metrics(raw: bytes) -> dict:
    book = insp.parse_playbook_resource(raw)
    body = raw[insp.RESOURCE_HEADER_SIZE:]
    fs, ps = ordinary_indices(book, body)
    code_of = {}
    for ci in book.categories:
        code_of[ci.index] = body[insp.CATEGORY_BASE + ci.index * insp.CATEGORY_SIZE + 4] & 0x3F
    first_form = {}
    links = []
    triples, personnel = Counter(), Counter()
    for f in book.formations:
        if f.index not in fs:
            continue
        rec = lib.formation_record(body, f.index)
        triples[((rec.flags >> 21) & 7, (rec.flags >> 24) & 7, (rec.flags >> 27) & 7)] += 1
        cat = lib.formation_category(body, f.index)
        personnel[code_of.get(cat)] += 1
        n = 0
        for link in f.play_links:
            if link.play_index in ps:
                n += 1
                first_form.setdefault(link.play_index, f.index)
        links.append(n)
    routes, segs, kinds = Counter(), Counter(), Counter()
    max_len = 0
    shapes, concepts, classes, words = set(), Counter(), Counter(), Counter()
    play_hashes = []
    for pi in sorted(ps):
        flags, chains = lib.play_chains(body, pi)
        words[flags] += 1
        cls = flags & 0xF000
        classes["quick" if cls & 0x8000 == 0 and cls & 0x6000 == 0x2000 else
                "dropback" if cls & 0x6000 == 0x6000 else "run" if cls & 0x8000 else "other"] += 1
        if flags & 0x1000:
            classes["trick"] += 1
        if flags & 0x200000:
            classes["play_action"] += 1
        concepts[concept_name(book.plays[pi].name)] += 1
        raw_chains = [b"".join(nodes) for _d, nodes in chains]
        shapes.add(tuple(sorted(raw_chains)))
        play_hashes.append(hashlib.sha256(struct.pack("<I", flags) + b"".join(raw_chains)).hexdigest())
        fi = first_form.get(pi)
        if fi is None:
            continue
        cats = lib.category_positions(body, lib.formation_category(body, fi))
        for s in range(6, 11):
            if cats[s] & 31 not in RECEIVERS:
                continue
            nodes = [codec.Node.from_bytes(n) for n in chains[s][1]]
            route = [(int(n.operands[0]), round(n.operands[2] / codec.FT_CM)) for n in nodes if n.op == 0x12]
            if not route or any(t == 9 for t, _ in route):
                continue
            routes[tuple(route)] += 1
            max_len = max(max_len, len(route))
            for seg in route:
                segs[seg] += 1
                kinds[seg[0]] += 1
    return dict(formations=len(fs), plays=len(ps), links=sum(links), menu_min=min(links), menu_max=max(links),
                menu_mean=round(sum(links) / len(links), 2), route_chains=sum(routes.values()),
                distinct_routes=len(routes), distinct_segments=len(segs), segment_types=sorted(kinds),
                max_route_segments=max_len, distinct_shapes=len(shapes), concepts=len(concepts),
                most_copies_of_one_concept=max(concepts.values()), header_words=len(words),
                classes=dict(classes), situation_combos=len(triples),
                personnel={str(k): v for k, v in sorted(personnel.items(), key=lambda kv: (kv[0] is None, kv[0]))},
                heavy_formations=sum(v for k, v in personnel.items() if k is not None and k <= 2),
                spread_formations=sum(v for k, v in personnel.items() if k is not None and k >= 8),
                flea_flicker=sum(v for k, v in concepts.items() if "flea" in k.lower()),
                _routes=[list(map(list, r)) for r in routes], _play_hashes=play_hashes,
                _concept_names=sorted(concepts))


def league(label: str, directory: Path) -> dict:
    per = {}
    all_routes, all_segs, all_kinds = set(), set(), set()
    owner = Counter()
    for team in TEAMS:
        path = directory / f"{team}.play"
        m = book_metrics(path.read_bytes())
        per[team] = m
        for r in m["_routes"]:
            key = tuple(map(tuple, r))
            all_routes.add(key)
            for seg in key:
                all_segs.add(seg)
                all_kinds.add(seg[0])
        for h in set(m["_play_hashes"]):
            owner[h] += 1
    for team, m in per.items():
        hashes = m.pop("_play_hashes")
        m["plays_shared_with_another_team"] = sum(1 for h in hashes if owner[h] > 1)
        m["plays_unique_to_team"] = sum(1 for h in hashes if owner[h] == 1)
        m.pop("_routes")
    totals = dict(distinct_routes=len(all_routes), distinct_segments=len(all_segs), segment_types=sorted(all_kinds),
                  plays=sum(m["plays"] for m in per.values()),
                  shared_plays=sum(m["plays_shared_with_another_team"] for m in per.values()),
                  mean_concepts=round(sum(m["concepts"] for m in per.values()) / 32, 1),
                  mean_menu=round(sum(m["links"] for m in per.values()) / sum(m["formations"] for m in per.values()), 2),
                  quick_plays=sum(m["classes"].get("quick", 0) for m in per.values()),
                  play_action_plays=sum(m["classes"].get("play_action", 0) for m in per.values()),
                  trick_plays=sum(m["classes"].get("trick", 0) for m in per.values()),
                  mean_situation_combos=round(sum(m["situation_combos"] for m in per.values()) / 32, 1),
                  books_with_heavy=sum(1 for m in per.values() if m["heavy_formations"]),
                  books_with_flea=sum(1 for m in per.values() if m["flea_flicker"]),
                  max_route_segments=max(m["max_route_segments"] for m in per.values()))
    return dict(label=label, totals=totals, teams=per)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pairs", nargs="+", help="LABEL DIR pairs")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if len(args.pairs) % 2:
        ap.error("give LABEL DIR pairs")
    out = {}
    for label, directory in zip(args.pairs[::2], args.pairs[1::2]):
        out[label] = league(label, Path(directory))
        print(label, json.dumps(out[label]["totals"]))
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
