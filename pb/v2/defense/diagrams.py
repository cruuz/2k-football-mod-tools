#!/usr/bin/env python3
"""Draw every distinct v2 defensive front from the generated data (pb/v2/defense/out/<TEAM>.json) as SVG.

Each picture shows the offensive line (C, G, T and an inline TE on the strength), every defender at its exact
formation spot with its technique label, and the 1.7 yd spacing rule.  Usage:
  python3 pb/v2/defense/diagrams.py OUT_DIR
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from mod_editor.core import nfl2k5_defense_lint as dlint  # noqa: E402

YD = 91.44
KIND = {12: 'DE', 13: 'DT', 14: 'MLB', 15: 'OLB', 16: 'FS', 17: 'SS', 18: 'CB'}
COLOR = {'DE': '#c0392b', 'DT': '#c0392b', 'MLB': '#2471a3', 'OLB': '#2471a3', 'FS': '#1e8449', 'SS': '#1e8449',
         'CB': '#1e8449'}


def svg(title: str, positions, codes, subtitle: str = '') -> str:
    sc = 24                                  # px per yard
    w, h = 18 * 2 * sc, 17 * sc
    cx, base = w / 2, h - 3.0 * sc
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
           'font-family="Helvetica, Arial, sans-serif">',
           f'<rect width="{w}" height="{h}" fill="#f4f1e8"/>',
           f'<line x1="0" y1="{base}" x2="{w}" y2="{base}" stroke="#555" stroke-dasharray="6 4"/>',
           f'<text x="10" y="20" font-size="15" font-weight="bold">{title}</text>',
           f'<text x="10" y="38" font-size="11" fill="#444">{subtitle}</text>']
    for x, lab in ((-304.8, 'T'), (-152.4, 'G'), (0, 'C'), (152.4, 'G'), (304.8, 'T'), (-457.2, 'TE')):
        px = cx + x / YD * sc
        out.append(f'<rect x="{px - 9}" y="{base + 6}" width="18" height="18" rx="3" fill="#ddd" stroke="#888"/>'
                   f'<text x="{px}" y="{base + 19}" font-size="9" text-anchor="middle">{lab}</text>')
    for s, ((x, z), code) in enumerate(zip(positions, codes)):
        if abs(x) > 17 * YD or z > 14 * YD:
            continue
        kind = KIND.get(code & 31, '?')
        px, py = cx + x / YD * sc, base - z / YD * sc
        dl = kind in ('DE', 'DT')
        out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="10" fill="{COLOR.get(kind, "#777")}" '
                   f'stroke="#222" stroke-width="{2 if dl else 1}"/>'
                   f'<text x="{px:.1f}" y="{py + 3.5:.1f}" font-size="8" fill="white" text-anchor="middle">{kind}</text>')
        if dl or (z <= 1.2 * YD):
            ax = abs(x)
            gap = 'A gap' if ax < 152 else 'B gap' if ax < 304 else 'C gap' if ax < 457 else 'edge'
            label = dlint.technique(x) if dl else f'{gap} (up)'
            out.append(f'<text x="{px:.1f}" y="{py - 14:.1f}" font-size="9" text-anchor="middle" fill="#333">{label}</text>')
    out.append(f'<text x="{w - 10}" y="{h - 8}" font-size="10" text-anchor="end" fill="#666">strength (TE side) on the left; '
               'one grid unit = 1 yd; DL hands down, others standing</text>')
    out.append('</svg>')
    return '\n'.join(out)


def distinct_fronts(out_dir: Path = HERE / 'out'):
    seen = {}
    for f in sorted(out_dir.glob('*.json')):
        if f.name in ('manifest.json', 'offense_pins.json'):
            continue
        d = json.loads(f.read_text())
        for key, r in d['roles'].items():
            sig = json.dumps([r['positions'], r['codes']])
            seen.setdefault(sig, dict(name=r['name'], role=key, family=r['family'], teams=[], positions=r['positions'],
                                      codes=r['codes'], situation=r['situation']))['teams'].append(d['team'])
    return list(seen.values())


def main(argv):
    dest = Path(argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, row in enumerate(sorted(distinct_fronts(), key=lambda r: (r['name'], len(r['teams'])))):
        slug = f"{n:02d}_{row['name'].replace(' ', '_').replace('/', '-')}"
        sub = f"{row['family']} line; teams: {', '.join(row['teams'])}; CPU ratings short/medium/long {row['situation']}"
        (dest / f'{slug}.svg').write_text(svg(row['name'], row['positions'], row['codes'], sub), newline='\n')
        view = dlint.DefenseFormation(row['name'], row['positions'], row['codes'],
                                      [3 if (c & 31) in (12, 13) else 1 for c in row['codes']])
        rows.append(dict(file=f'{slug}.svg', name=row['name'], teams=row['teams'], family=row['family'],
                         ascii=dlint.front_diagram(view),
                         lint=[x.code for x in dlint.formation_findings(view)]))
    (dest / 'index.json').write_text(json.dumps(rows, indent=1) + '\n', newline='\n')
    print(len(rows), 'fronts drawn')


if __name__ == '__main__':
    main(sys.argv)
