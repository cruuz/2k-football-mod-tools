#!/usr/bin/env python3
"""gaptable.py : read audit/<TEAM>.json, print and save the ranked gap table (audit/gap_table.json, audit/gap_table.md-like text)."""
import json, glob, sys
from pathlib import Path
A = Path('/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/audit')
W = {'major': 3, 'minor': 1}
GAME = {'jersey_base', 'pants_base', 'shoulder_sleeve_panels', 'sleeve_stripes', 'pants_stripes', 'number_colour_outline', 'socks', 'helmet_jersey_match'}
rows = []
OV = json.load(open(A / 'overrides.json')) if (A / 'overrides.json').exists() else {}
noref = {}
for f in sorted(A.glob('[A-Z]*.json')):
    if f.name.startswith('gap'): continue
    d = json.load(open(f))
    noref[d['team']] = d.get('no_reference', [])
    for k in d.get('kits', []):
        el = k.get('elements', {})
        for e, v in OV.get(k['selector'], {}).items():
            if e in el: el[e] = dict(el[e], verdict=v, note='(corrected: ' + OV[k['selector']].get('_why', '') + ') ' + el[e].get('note', ''))
        if k['selector'] in OV.get('_gp', {}): k['gameplay_visibility'] = OV['_gp'][k['selector']]
        if k['selector'] in OV.get('_cu', {}): k['closeup_visibility'] = OV['_cu'][k['selector']]
        maj = [e for e, v in el.items() if v.get('verdict') == 'major']; mnr = [e for e, v in el.items() if v.get('verdict') == 'minor']
        score = sum(3 * (2 if e in GAME else 1) for e in maj) + sum(1 * (2 if e in GAME else 1) for e in mnr)
        vis = 2 * k.get('gameplay_visibility', 0) + k.get('closeup_visibility', 0)
        rows.append(dict(team=d['team'], selector=k['selector'], also=k.get('also', []), look=k.get('look'), gp=k.get('gameplay_visibility', 0),
                         cu=k.get('closeup_visibility', 0), major=maj, minor=mnr, score=score, rank=vis * 10 + score, top=k.get('top_fixes', []),
                         notes={e: el[e].get('note', '') for e in maj + mnr}, other=k.get('anything_else', [])))
rows.sort(key=lambda r: -r['rank'])
json.dump(dict(rows=rows, no_reference=noref), open(A / 'gap_table.json', 'w'), indent=1)
n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
for i, r in enumerate(rows[:n], 1):
    top = [t for t in (r['top'] or ['-']) if not (r['selector'] in OV and any(w in t.lower() for w in ('pants instead', 'black pants', 'purple pants', 'blue pants', 'not white', 'black socks')))] or ['-']
    print(f"{i:3d} {r['team']:3s} {r['selector']:6s} gp{r['gp']} cu{r['cu']} maj[{','.join(r['major'])}] min[{','.join(r['minor'])}] | {top[0][:170]}")
print(len(rows), 'kits audited')
