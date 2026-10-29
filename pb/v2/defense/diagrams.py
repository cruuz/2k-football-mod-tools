#!/usr/bin/env python3
"""Draw every distinct v2 defensive front from the generated data (pb/v2/defense/out/<TEAM>.json) as SVG, or (b779 dp1,
``sheet``) a contact sheet PNG of a club's whole defensive menus from its final PLAY book.

Each picture shows the offensive line (C, G, T and an inline TE on the strength), every defender at its exact
formation spot with its technique label, and the 1.7 yd spacing rule.  Usage:
  python3 pb/v2/defense/diagrams.py OUT_DIR
  python3 pb/v2/defense/diagrams.py sheet BOOK_DIR OUT_DIR TEAM [TEAM ...]
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


# ---------------------------------------------------------------------------------------------------------------
# b779 dp1: contact sheet of a club's defensive menus (every formation, every coverage call), from a final PLAY book.
# ---------------------------------------------------------------------------------------------------------------
def _font(size, bold=False):
    from PIL import ImageFont
    name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    for d in ('/usr/share/fonts/truetype/dejavu', '/Library/Fonts', 'C:/Windows/Fonts'):
        try:
            return ImageFont.truetype(f'{d}/{name}', size)
        except OSError:
            continue
    return ImageFont.load_default()


def panel(draw, ox, oy, w, h, rec, kinds, chains, title, sub, presnap_shell=''):
    """One call: defenders at their PRE-SNAP spots (formation spot + Defense Start), lines to their post-snap jobs:
    rushers to the line (red), deep zones (blue, filled), underneath zones (teal), man (orange dashes, a short arrow
    toward the receiver side)."""
    from mod_editor.core import nfl2k5_defense_calls as dc
    sc = w / (40 * YD)                          # 40 yd wide panel
    cx, los = ox + w / 2, oy + h - 16
    sz = (h - 16 - 40) / (20 * YD)              # 20 yd deep below the title lines
    def px(x, z):
        return cx + x * sc, los - min(z, 21 * YD) * sz
    draw.rectangle([ox, oy, ox + w, oy + h], fill='#f4f1e8', outline='#999')
    draw.line([ox, los, ox + w, los], fill='#555', width=1)
    for x in (-304.8, -152.4, 0, 152.4, 304.8, -457.2):
        a, b = px(x, -60)
        draw.rectangle([a - 4, b - 4, a + 4, b + 4], fill='#ddd', outline='#888')
    for s in range(11):
        spot = (rec.slots[s].x[0], rec.slots[s].z[0])
        pre = dc.presnap_point(spot, chains[s]) or spot
        x0, y0 = px(*pre)
        op, v = dc._first(chains[s])
        k = kinds[s]
        if op == 0x0B:
            lane = int(v[1]) if v else 8
            lx = (lane - 8) * 76.2
            x1, y1 = px(lx, -40)
            draw.line([x0, y0, x1, y1], fill='#c0392b', width=2)
        elif op == 0x0D:
            x1, y1 = px(v[0], v[1])
            deep = v[1] >= dc.DEEP_CM
            draw.line([x0, y0, x1, y1], fill='#1f4e9c' if deep else '#138a72', width=2)
            r = 7 if deep else 5
            draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill='#1f4e9c' if deep else '#138a72')
        elif op == 0x0E:
            x1, y1 = x0 + (12 if pre[0] >= 0 else -12), y0 - 14
            for t in range(0, 10, 3):
                draw.line([x0 + (x1 - x0) * t / 10, y0 + (y1 - y0) * t / 10, x0 + (x1 - x0) * (t + 2) / 10,
                           y0 + (y1 - y0) * (t + 2) / 10], fill='#d35400', width=2)
        col = '#c0392b' if k in (12, 13) else '#2471a3' if k in (14, 15) else '#1e8449'
        draw.ellipse([x0 - 5, y0 - 5, x0 + 5, y0 + 5], fill=col, outline='#222')
    f1, f2 = _font(12, True), _font(10)
    draw.text((ox + 5, oy + 3), title[:30], fill='#111', font=f1)
    draw.text((ox + 5, oy + 18), sub[:44], fill='#444', font=f2)
    if presnap_shell:
        draw.text((ox + w - 5, oy + 3), presnap_shell, fill='#7b241c', font=f2, anchor='ra')


def sheet(team: str, resource: bytes, dest: Path, max_per_formation: int = 24) -> Path:
    """Contact sheet PNG of ``team``'s defensive menus (formations of types 4-6 and their coverage calls)."""
    from PIL import Image, ImageDraw
    from mod_editor.core import nfl2k5_playbook_inspector as ip
    from mod_editor.core import nfl2k5_play_library as lib
    from mod_editor.core import nfl2k5_defense_calls as dc
    book = ip.parse_playbook_resource(resource)
    body = resource[32:]
    blocks = []
    for f in book.formations:
        rec = lib.formation_record(body, f.index)
        if rec.type_code not in (4, 5, 6):
            continue
        kinds = [c & 31 for c in lib.category_positions(body, lib.formation_category(body, f.index))]
        pairs = lib.defense_pairs(book, body, f.index)
        fronts = []
        seen = {}
        for fr, cv in pairs:
            if fr not in fronts:
                fronts.append(fr)
            seen.setdefault(cv, fr)
        items = []
        for cv, fr in list(seen.items())[:max_per_formation]:
            c = dc.classify(book, body, f.index, fr, cv)
            chains = lib.effective_defense(lib.decoded_chains(body, fr), lib.decoded_chains(body, cv))
            tag = f"{c.family} {'blitz ' if c.blitz else ''}{'sim ' if c.sim else ''}{'man' if c.man else 'zone'}"
            items.append((rec, kinds, chains, c.coverage_name, tag + f' | {c.rushers} rush',
                          f'shows {c.presnap}-high' if c.presnap else ''))
        front_names = ', '.join(book.plays[i].name.strip() for i in fronts[:10])
        blocks.append((f.name.strip(), front_names, items))
    cols, pw, ph = 6, 250, 205
    head = 58
    height = 70 + sum(head + ph * ((len(it) + cols - 1) // cols) for _, _, it in blocks)
    img = Image.new('RGB', (cols * pw + 20, height), '#ffffff')
    d = ImageDraw.Draw(img)
    d.text((10, 8), f'{team} defense: every formation and coverage call (pre-snap spots, post-snap jobs)', fill='#000',
           font=_font(20, True))
    d.text((10, 36), 'red: rush lane | blue dot: deep zone | teal dot: underneath zone | orange dashes: man | '
           'upper right: shell shown before the snap', fill='#333', font=_font(12))
    y = 70
    for name, fronts, items in blocks:
        d.text((10, y + 4), name, fill='#000', font=_font(16, True))
        d.text((10, y + 26), 'Fronts: ' + fronts, fill='#333', font=_font(12))
        y += head
        for i, (rec, kinds, chains, title, sub, shell_txt) in enumerate(items):
            panel(d, 10 + (i % cols) * pw, y + (i // cols) * ph, pw - 6, ph - 6, rec, kinds, chains, title, sub, shell_txt)
        y += ph * ((len(items) + cols - 1) // cols)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def main(argv):
    if len(argv) > 1 and argv[1] == 'sheet':
        # diagrams.py sheet BOOK_DIR OUT_DIR TEAM [TEAM ...]
        book_dir, out_dir = Path(argv[2]), Path(argv[3])
        for team in argv[4:]:
            print(sheet(team, (book_dir / f'{team}.play').read_bytes(), out_dir / f'{team}_defense_sheet.png'))
        return
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
