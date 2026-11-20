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
# the number-font / nameplate check and the swoosh check are their own columns
def side(folder, key):
    out = {}
    for f in sorted((A / folder).glob('[A-Z]*.json')):
        try: d = json.load(open(f))
        except Exception: continue
        for k in d.get('kits', []):
            for sel in [k['selector']] + list(k.get('also') or []):
                out[sel] = k
    return out
fonts, swoosh = side('fonts', 'font_verdict'), side('swoosh', 'verdicts')
byrow = {r['selector']: r for r in rows}
for sel, k in fonts.items():
    if sel not in byrow:
        if k.get('font_verdict') in ('major', 'minor') and sel == k['selector']:
            rows.append(dict(team=sel[:2], selector=sel, also=k.get('also', []), look=k.get('look'), gp=0, cu=0, major=[], minor=[], score=0, rank=0, top=[], notes={}, other=[]))
            byrow[sel] = rows[-1]
        else: continue
    r = byrow[sel]; ch = k.get('checks', {})
    r['font'] = dict(verdict=k.get('font_verdict'), fix=k.get('fix'), nameplate=(ch.get('nameplate') or {}).get('verdict'),
                     nameplate_note=(ch.get('nameplate') or {}).get('note'), digits_needed=k.get('digits_needed'))
    worst = 'major' if 'major' in (r['font']['verdict'], r['font']['nameplate']) else 'minor' if 'minor' in (r['font']['verdict'], r['font']['nameplate']) else 'ok'
    r['rank'] += {'major': 26, 'minor': 6, 'ok': 0}[worst]
for sel, k in swoosh.items():
    if sel in byrow:
        v = k.get('verdicts', {}); bad = {e: x.get('verdict') for e, x in v.items() if x.get('verdict') in ('major', 'minor')}
        byrow[sel]['swoosh'] = dict(verdicts=bad, fix=k.get('fix'))
        byrow[sel]['rank'] += 12 * sum(1 for x in bad.values() if x == 'major') + 3 * sum(1 for x in bad.values() if x == 'minor')
rows.sort(key=lambda r: -r['rank'])
json.dump(dict(rows=rows, no_reference=noref), open(A / 'gap_table.json', 'w'), indent=1)
n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
for i, r in enumerate(rows[:n], 1):
    top = [t for t in (r['top'] or ['-']) if not (r['selector'] in OV and any(w in t.lower() for w in ('pants instead', 'black pants', 'purple pants', 'blue pants', 'not white', 'black socks')))] or ['-']
    f = r.get('font') or {}; w = r.get('swoosh') or {}
    print(f"{i:3d} {r['team']:3s} {r['selector']:6s} gp{r['gp']} cu{r['cu']} maj[{','.join(r['major'])}] min[{','.join(r['minor'])}] FONT[{f.get('verdict', '-')}/name {f.get('nameplate', '-')}] SWOOSH[{','.join(k + ':' + v for k, v in (w.get('verdicts') or {}).items()) or '-'}] | {top[0][:150]}" + (f" || font: {str(f.get('fix'))[:150]}" if f.get('verdict') in ('major', 'minor') else ''))
print(len(rows), 'kits audited')
