#!/usr/bin/env python3
"""Expected CPU defensive call mix per team, from the shipped coach-profile rings, against the real 2025 rates (b779 dp1).

How the CPU picks a defensive call in a SOFTDRINK build (PROVED OFFLINE, retail XBE 73105b17 plus the coach_ai owner):
  * modes 4..7 (Play Now, Season, Franchise, playoffs), current-NFL CPU side, ordinary play-call phase: the coach_ai
    hook at 0x20B83D calls the retail VIP defense pick 0x17DFC0.  0x17DFC0 asks 0xF7450 for ring ``bin * 5 + group``
    (bin from 0xF7010: down and distance, 0 short / 1 medium / 2 long, none on 4th down; group from the offense's
    lined-up personnel category code: 0 unknown, 1 codes 0-2, 2 codes 3-4, 3 codes 5-7, 4 codes 8-10) and draws one
    of the ring's four (formation, front, coverage) entries uniformly, skipping the entry equal to the last call;
    the coach_ai kernel publishes it through the native tail 0x20B977;
  * otherwise (4th down, no ring, coach_ai off, explicit modes): the native lottery 0x20B8D0: 0x20B400 -> 0x208480
    maps the offense personnel to a defensive category (codes 0-4 base 13, 5-7 nickel 14, 8-10 dime 15, goal line 11
    inside the 5, prevent 16 from 0x208420), 0x2093F0 takes that exact category (curve 1 / 0.01 / 0, cubed; same-code
    categories are equal), 0x2081B0 draws a formation on its 0x207EF0 short / medium / long rating (exponent 1),
    0x20A7F0 and 0x20AA40 draw the front and the coverage on their header bands (bits 9-11, curve 0x50AFE0, cubed).

This tool reads a final PLAY resource (with its coach tag), decodes the fifteen rings and classifies every entry with
``nfl2k5_defense_calls``.  Each ring is weighted by the share of the team's 2025 snaps in its cell
(``pb/research/defense_situational_2025.json``, the DC profile's baseline team); the unknown-personnel rings (group 0)
are reported separately because how often the defense calls before the offense lines up is not measured.

  python3 pb/v2/defense/cpu_callmix.py BOOK_DIR [--teams TEN,PIT] [--out table.json]
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for p in (str(ROOT), str(ROOT / 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from mod_editor.core import nfl2k5_playbook_inspector as ip  # noqa: E402
from mod_editor.core import nfl2k5_defense_calls as calls  # noqa: E402
from mod_editor.core import nfl2k5_defense_rings as rings  # noqa: E402

FAMILIES = ('C0', 'C1', '2M', 'C2', 'C3', 'C4', 'C6')
TEAMS = ('ARZ', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC',
         'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'OAK', 'PHI', 'PIT', 'SD', 'SEA', 'SF', 'STL', 'TB', 'TEN', 'WAS')


def decode_rings(resource: bytes) -> list[list[tuple[int, int, int]]] | None:
    tag = resource[32 + 0x13000:32 + 0x13000 + 896]
    if tag[:8] != b'COACHAI1':
        return None
    p = tag[128:][480:660]
    return [[tuple(p[(i * 4 + j) * 3:(i * 4 + j) * 3 + 3]) for j in range(4)] for i in range(15)]


def mix(entries: list[tuple[float, calls.Call]]) -> dict:
    z = sum(w for w, _ in entries) or 1.0
    out = Counter()
    for w, c in entries:
        out['p_' + c.personnel] += w / z
        out['f_' + c.family] += w / z
        out['man'] += c.man * w / z
        out['blitz'] += c.blitz * w / z
        out['sim'] += c.sim * w / z
        out['single'] += (c.postsnap == 'one') * w / z
        out['presnap_two'] += (c.presnap == 'two') * w / z
        out['disguise'] += c.disguise * w / z
        out['bear'] += c.bear * w / z
    return {k: round(v, 4) for k, v in sorted(out.items())}


def team_table(team: str, resource: bytes, cells: dict) -> dict:
    book = ip.parse_playbook_resource(resource)
    body = resource[32:]
    rs = decode_rings(resource)
    if rs is None:
        return dict(team=team, error='no coach tag')
    known, unknown, per_bin = [], [], {0: [], 1: [], 2: []}
    distinct = set()
    for i, ring in enumerate(rs):
        b, g = divmod(i, 5)
        cs = [calls.classify(book, body, f, fr, cv) for f, fr, cv in ring]
        distinct.update((c.formation, c.front, c.coverage) for c in cs)
        if g == 0:
            unknown.extend((1.0, c) for c in cs)
            continue
        w = cells.get(f'{b}{g}', {}).get('snaps', 0)
        known.extend((w / 4, c) for c in cs)
        per_bin[b].extend((w / 4, c) for c in cs)
    return dict(team=team, model=mix(known), model_unknown=mix(unknown),
                model_by_bin={str(b): mix(v) for b, v in per_bin.items()},
                real=rings.real_rates(cells), real_by_bin={str(b): rings.real_rates(cells, b) for b in (0, 1, 2)},
                distinct_calls=len(distinct),
                ring_formations=dict(Counter(calls.classify(book, body, *e).formation_name for r in rs for e in r)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('book_dir', type=Path, help='directory of <TEAM>.play final PLAY resources (with coach tags)')
    ap.add_argument('--teams', default=','.join(TEAMS))
    ap.add_argument('--out', type=Path)
    args = ap.parse_args(argv)
    identity = rings.load_identity()
    rows = []
    for t in args.teams.split(','):
        path = args.book_dir / f'{t}.play'
        if not path.is_file():
            continue
        row = team_table(t, path.read_bytes(), identity['teams'][t]['cells'])
        rows.append(row)
        m, r = row.get('model', {}), row.get('real', {})
        print(f"{t:4} base {m.get('p_base', 0):.2f}/{r.get('p_base', 0):.2f} nickel {m.get('p_nickel', 0):.2f}/"
              f"{r.get('p_nickel', 0):.2f} dime {m.get('p_dime', 0):.2f}/{r.get('p_dime', 0):.2f} man {m.get('man', 0):.2f}/"
              f"{r.get('man', 0):.2f} blitz {m.get('blitz', 0):.2f}/{r.get('blitz', 0):.2f} single {m.get('single', 0):.2f}/"
              f"{r.get('single', 0):.2f} C0 {m.get('f_C0', 0):.2f}/{r.get('f_C0', 0):.2f} distinct {row.get('distinct_calls')}",
              flush=True)
    if args.out:
        args.out.write_text(json.dumps(rows, indent=1) + '\n', newline='\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
