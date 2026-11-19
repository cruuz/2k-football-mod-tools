#!/usr/bin/env python3
"""marks_s2.py : re-read the mark audit (audit/marks/<TEAM>.json) against the calibrated scale.
The audits compared each mark with the collar shield as painted (8 texels = 2.2 cm), but the shield itself is painted too
small: on sharp game photographs it is 0.141 of the front number's height (16 players), which on the game's player is
3.3 cm = 12 texels. So a mark's true size is (its real width in shield widths) x 3.3 cm. Prints, per mark that has a real
measurement against the shield, the game width, the true width and the scale needed, worst first; writes
audit/marks/s2.json."""
import json, glob, os, statistics
U = '/home/noah/2k-worktrees/.b77-scratch/b81/uniforms/'
SHIELD_CM = 3.3
rows = []
for f in sorted(glob.glob(U + 'audit/marks/*.json')):
    d = json.load(open(f))
    if not isinstance(d, dict) or not isinstance(d.get('kits'), list): continue
    for k in d['kits']:
        if not isinstance(k, dict): continue
        for name, m in (k.get('marks') or {}).items():
            if not isinstance(m, dict) or name == 'collar_shield': continue
            g = m.get('game') or {}
            real = [r.get('ratio') for r in (m.get('real') or []) if isinstance(r, dict) and r.get('ref') == 'collar_shield'
                    and isinstance(r.get('ratio'), (int, float))]
            if not real or not isinstance(g, dict): continue
            cm = g.get('cm_w') or (g.get('w') * 0.275 if g.get('texture') == 'torso' and g.get('w') else None)
            if not cm: continue
            true = statistics.median(real) * SHIELD_CM
            rows.append(dict(team=d['team'], selector=k['selector'], also=k.get('also', []), mark=name, what=m.get('what', '')[:50],
                             game_cm=round(cm, 1), game_w=g.get('w'), real_ratios=real, true_cm=round(true, 1),
                             scale=round(true / cm, 2), audit_verdict=m.get('verdict')))
for r in rows:
    s = r['scale']; r['s2'] = 'ok' if 0.85 <= s <= 1.18 else 'minor' if 0.7 <= s <= 1.43 else 'major'
rows.sort(key=lambda r: abs(1 - r['scale']) if r['scale'] < 1 else abs(1 - 1 / r['scale']), reverse=True)
json.dump(rows, open(U + 'audit/marks/s2.json', 'w'), indent=1)
import collections
print(collections.Counter(r['s2'] for r in rows))
for r in rows:
    if r['s2'] != 'ok':
        print('%-3s %-5s %-14s %-5s game %5.1f cm  true %5.1f cm  x%.2f  (was %s; real %s) %s' % (
            r['team'], r['selector'], r['mark'], r['s2'], r['game_cm'], r['true_cm'], r['scale'], r['audit_verdict'],
            ','.join('%.2f' % x for x in r['real_ratios']), r['what']))
