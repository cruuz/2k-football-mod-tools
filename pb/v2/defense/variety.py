#!/usr/bin/env python3
"""How different the 32 club defenses are from each other (b779 dp1).  Reads final PLAY resources (<TEAM>.play).

Book measures (the menus a user sees and the CPU draws from):
  * coverage scripts: distinct coverage chain sets league-wide, and the share of a book's coverage records no other
    club has (team-unique);
  * front geometry: distinct defensive formation alignments (slot spots) league-wide and per family;
  * front calls: distinct (call name, rush lanes, band) front records league-wide and distinct front-call menus;
  * shells: single-high calls shown from two-high before the snap (disguise) per book.
Ring measures (the CPU's own calls, ``cpu_callmix.decode_rings``): distinct calls per club and the spread of the
clubs' expected personnel / blitz / man / single-high rates (standard deviation across the 32 clubs).

  python3 pb/v2/defense/variety.py BOOK_DIR [--out variety.json]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (str(ROOT), str(ROOT / 'tools'), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_play_library as lib  # noqa: E402
from mod_editor.core import nfl2k5_defense_calls as calls  # noqa: E402
import cpu_callmix as cm  # noqa: E402


def key(chains) -> str:
    return json.dumps([[(n[0], [round(float(x), 1) for x in n[1]]) for n in c] if c else None for c in chains])


def book_rows(team: str, resource: bytes) -> dict:
    book = ip.parse_playbook_resource(resource)
    body = resource[32:]
    cov, fronts, forms, menus = set(), set(), set(), []
    shells = Counter()
    for f in book.formations:
        rec = lib.formation_record(body, f.index)
        if rec.type_code not in (4, 5, 6):
            continue
        forms.add(json.dumps([(round(s.x[0]), round(s.z[0])) for s in rec.slots]))
        menu = []
        seen = set()
        for front, cover in lib.defense_pairs(book, body, f.index):
            if front not in seen:
                seen.add(front)
                p = book.plays[front]
                sig = (p.name.strip(), key(lib.decoded_chains(body, front)), (p.flags_or_id >> 9) & 7)
                fronts.add(sig)
                menu.append(sig[0])
            ck = key(lib.decoded_chains(body, cover))
            if ck in cov:
                continue
            cov.add(ck)
            if 'bear' not in f.name.lower():
                c = calls.classify(book, body, f.index, front, cover)
                shells[(c.postsnap, c.presnap)] += 1
        menus.append(tuple(menu))
    single = shells[('one', 'two')] + shells[('one', 'one')] + shells[('one', '')]
    return dict(team=team, coverage=cov, fronts=fronts, formations=forms, front_menus=set(menus),
                disguise=round(shells[('one', 'two')] / single, 3) if single else 0.0, coverage_records=len(cov))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book_dir', type=Path)
    ap.add_argument('--out', type=Path)
    a = ap.parse_args(argv)
    rows = [book_rows(t, (a.book_dir / f'{t}.play').read_bytes()) for t in cm.TEAMS if (a.book_dir / f'{t}.play').is_file()]
    owners = defaultdict(set)
    for r in rows:
        for k in r['coverage']:
            owners[k].add(r['team'])
    unique = {r['team']: round(sum(len(owners[k]) == 1 for k in r['coverage']) / len(r['coverage']), 3) for r in rows}
    out = dict(books=len(rows),
               league_distinct_coverage_scripts=len(owners),
               mean_coverage_records_per_book=round(statistics.mean(r['coverage_records'] for r in rows), 1),
               mean_team_unique_coverage_share=round(statistics.mean(unique.values()), 3),
               league_distinct_formation_alignments=len(set().union(*(r['formations'] for r in rows))),
               league_distinct_front_records=len(set().union(*(r['fronts'] for r in rows))),
               league_distinct_front_menus=len(set().union(*(r['front_menus'] for r in rows))),
               disguise_share=dict((r['team'], r['disguise']) for r in rows),
               team_unique_coverage_share=unique)
    identity = cm.rings.load_identity()
    ring_rows = []
    for r in rows:
        t = cm.team_table(r['team'], (a.book_dir / f"{r['team']}.play").read_bytes(), identity['teams'][r['team']]['cells'])
        if 'model' in t:
            ring_rows.append(t)
    if ring_rows:
        def sd(k):
            return round(statistics.pstdev(t['model'].get(k, 0) for t in ring_rows), 4)
        def err(k):
            return round(statistics.mean(abs(t['model'].get(k, 0) - t['real'].get(k, 0)) for t in ring_rows), 4)
        out['rings'] = dict(teams=len(ring_rows), mean_distinct_calls=round(statistics.mean(t['distinct_calls'] for t in ring_rows), 1),
                            min_distinct_calls=min(t['distinct_calls'] for t in ring_rows),
                            spread_sd={k: sd(k) for k in ('p_base', 'p_nickel', 'p_dime', 'blitz', 'man', 'single', 'f_C0', 'f_C4', 'f_C6')},
                            mean_abs_error_vs_2025={k: err(k) for k in ('p_base', 'p_nickel', 'p_dime', 'blitz', 'man', 'single', 'f_C0', 'f_C1', 'f_C2', 'f_C3', 'f_C4', 'f_C6')})
    print(json.dumps({k: v for k, v in out.items() if not isinstance(v, dict) or k == 'rings'}, indent=1))
    if a.out:
        a.out.write_text(json.dumps(out, indent=1) + '\n', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
