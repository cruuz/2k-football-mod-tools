"""Beta 76 sb: the 2026 ESPN bar's remaining states as sprite cells, traced from the broadcast (idempotent).

Reads read-only broadcast frames (never copied into the repository) and writes only derived cells into
data/nfl2k5_scorebug_sprite/template.png plus their rows in layout.json:

* espn_plate_mark: the white ESPN wordmark of the black no-down plate, the temporal median of the Giants at Rams
  off-air frames that show it (95 x 22 px at 913..1008 x 956..978 at 1080p), a label token "ESPN";
* label_Down: "Down" of the interim "3rd Down" label (Broncos at Chiefs, every settled "3rd Down" second), a label
  token "Down" at the other label glyphs' scale;
* timeout_tab: the TIMEOUT tab over the calling team's wing (Broncos at Chiefs, both away popups), one token "T";
* the FLAG cell's yellow set to the on-air plate (Giants at Rams, every FLAG frame), letters untouched;
* the two capsule dividers removed (ESPN's capsule has none).

Usage: python3 reports/b76_sb/author.py --gr <obs frames dir> --bc <frames_1s dir> [--check]
"""
from __future__ import annotations

import argparse, io, json, subprocess
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
FX, FY = 1 / 3, 448 / 1080                           # HUD texels per broadcast pixel at 16:9 after the 27/32 contraction


def texels(px, per):
    """Largest whole texel count that never exceeds the footprint (one mip, no minification)."""
    return max(1, int(px * per + 0.02))
BASE = '5836bf0f6'                                   # job/b76-sb's base: every run starts from these bytes
PLACE = {'espn_plate_mark': (0, 300), 'label_Down': (60, 300), 'timeout_tab': (0, 320)}
# Lab run 2 (2026-09-24): the game never draws the bar at the half, so HALFTIME (the capsule token this pass first
# traced) had no screen time; main removed it. The clock field keeps its box and the minute strip.


def _gr(gr, name):
    return np.asarray(Image.open(Path(gr) / name).convert('RGB')).astype(float)


def _bc(bc, t):
    return np.asarray(Image.open(Path(bc) / ('s_%05d.jpg' % (t + 1))).convert('RGB')).astype(float)


def _base(path):
    return subprocess.run(['git', '-C', str(ROOT), 'show', BASE + ':' + path], check=True, capture_output=True).stdout


def _ink(alpha):
    """Solid strokes at full coverage (the median of per-frame alphas stops short of 1), haze removed."""
    a = alpha / max(1e-6, np.percentile(alpha[alpha > 0.5], 90))
    a[a < 0.06] = 0
    return np.clip(a, 0, 1)


def _tight(alpha):
    ys, xs = np.where(alpha > 0.5)
    return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1


def _cell(alpha, rgb, size):
    """Area-filter a straight-alpha crop to a cell of `size` texels (premultiplied while filtering)."""
    a = np.clip(alpha, 0, 1)
    pm = np.dstack([rgb * a[..., None], a * 255])
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), 'RGBA').resize(size, Image.Resampling.BOX)
    p = np.asarray(im).astype(float)
    al = p[..., 3:4] / 255
    col = np.where(al > 0, p[..., :3] / np.maximum(al, 1e-6), 255)
    return Image.fromarray(np.dstack([np.clip(col, 0, 255), p[..., 3]]).round().astype(np.uint8), 'RGBA')


def espn_mark(gr):
    rows = json.load(open(Path(__file__).with_name('sources.json')))['gr_espn_plate_frames']
    stack = []
    for name in rows:
        a = _gr(gr, name)[950:984, 905:1015]
        m = a.min(2)
        if (m[6:28, 8:103] > 120).mean() < 0.05:        # mid-transition frames carry no mark yet
            continue
        stack.append(m)
    med = np.median(np.stack(stack), 0)
    bg = np.median(med[med < 60])
    alpha = _ink((med - bg) / (255 - bg))
    y0, y1, x0, x1 = _tight(alpha)
    crop = alpha[y0:y1, x0:x1]                                          # ink-tight: the mark sits alone on the plate
    box = [x0 + 905, y0 + 950, x1 + 905, y1 + 950]
    return _cell(crop, np.full(crop.shape + (3,), 255.0), (texels(crop.shape[1], FX), texels(crop.shape[0], FY))), dict(frames=len(stack), ink_box=box, background=round(float(bg), 1))


def down_word(bc, grammar):
    ts = [t for t, r in grammar.items() if r['plate'] == '3rd Down' and r['layout'] == 'full_bar']
    stack = []
    for t in ts:
        a = _bc(bc, t)[950:980, 860:1060]
        m = a.min(2)
        bgm = np.median(m[m < 110]) if (m < 110).any() else None
        if bgm is None:
            continue
        stack.append(np.clip((m - bgm) / (255 - bgm), 0, 1))
    med = _ink(np.median(np.stack(stack), 0))
    cols = np.where(med.max(0) > 0.45)[0]
    gaps = [(cols[i], cols[i + 1]) for i in range(len(cols) - 1) if cols[i + 1] - cols[i] > 6]
    start = gaps[-1][1] if gaps else cols[0]                            # "Down" follows the widest word gap
    word = med[:, start:cols[-1] + 1]
    y0, y1, x0, x1 = _tight(word)
    crop = word[y0:y1, x0:x1]
    # The other label glyphs are ink-tight cells drawn 30 px tall for ESPN's 23 px ink (12 texel rows, 0.332
    # texels per layout px across); "Down" takes the same scale so "3rd Down" keeps one face.
    layout = json.loads(_base('data/nfl2k5_scorebug_sprite/layout.json'))
    label = layout['glyph_sets']['label']['glyphs']
    tv_height = 23
    k = 30 / tv_height
    scale = np.median([(layout['cells'][label[t]['cell']]['box'][2] - layout['cells'][label[t]['cell']]['box'][0]) / label[t]['size'][0] for t in ('GOAL', 'Inch', 'nd')])
    width = crop.shape[1] * k
    return _cell(crop, np.full(crop.shape + (3,), 255.0), (texels(width, FX), texels(crop.shape[0] * k, FY))), dict(frames=len(stack), ink_box=[int(start + x0 + 860), int(y0 + 950), int(start + x1 + 860), int(y1 + 950)], tv_ink_height=int(y1 - y0), glyph_width=round(float(width), 3), scale=round(float(scale), 4))


def timeout_tab(bc):
    ts = list(range(7055, 7059)) + [3914, 3915]
    med = np.median(np.stack([_bc(bc, t)[900:942, 458:802] for t in ts]), 0)
    lum = med.mean(2)
    inside = np.zeros(lum.shape, bool)
    inside[2:41, 2:342] = True                                          # tab 460..799 x 902..940 with its rim
    return _cell(inside.astype(float), med, (texels(344, FX), texels(42, FY))), dict(frames=len(ts), fill=[int(v) for v in np.median(med[12:30, 10:100].reshape(-1, 3), 0)])


def flag_yellow(gr):
    rows = json.load(open(Path(__file__).with_name('sources.json')))['gr_flag_frames']
    px = np.concatenate([_gr(gr, n)[950:984, 840:1080].reshape(-1, 3) for n in rows])
    y = px[(px[:, 0] > 150) & (px[:, 1] > 150) & (px[:, 2] < 90)]
    return [int(v) for v in np.median(y, 0).round()], len(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gr', required=True); ap.add_argument('--bc', required=True); ap.add_argument('--grammar', required=True)
    args = ap.parse_args()
    grammar = {}
    for line in open(args.grammar):
        r = json.loads(line); grammar[r['t']] = r
    layout = json.loads(_base('data/nfl2k5_scorebug_sprite/layout.json'))
    tpl = Image.open(io.BytesIO(_base('data/nfl2k5_scorebug_sprite/template.png'))).convert('RGBA')
    t = np.asarray(tpl).astype(float)
    receipts = {}
    cells = {}
    cells['espn_plate_mark'], receipts['espn_plate_mark'] = espn_mark(args.gr)
    cells['label_Down'], receipts['label_Down'] = down_word(args.bc, grammar)
    cells['timeout_tab'], receipts['timeout_tab'] = timeout_tab(args.bc)
    # FLAG: keep the letters, move the yellow to the on-air plate.
    yellow, n = flag_yellow(args.gr)
    x0, y0, x1, y1 = layout['cells']['flag']['box']
    f = t[y0:y1, x0:x1].copy()
    ink = np.array([20.0, 20.0, 20.0]); old = np.array([255.0, 204.0, 0.0])
    k = np.clip((f[..., 0] - ink[0]) / (old[0] - ink[0]), 0, 1)[..., None]
    f[..., :3] = ink + k * (np.array(yellow, float) - ink)
    t[y0:y1, x0:x1] = f
    receipts['flag'] = dict(yellow=yellow, frames=n, before=[255, 204, 0])
    # Capsule dividers: the capsule cell's column 22 and the play-clock cell's column 0 take the white of their rows.
    for name, col, ref in (('capsule', 22, 23), ('red', 0, 1)):
        x0, y0, x1, y1 = layout['cells'][name]['box']
        t[y0:y1, x0 + col, :3] = t[y0:y1, x0 + ref, :3]
    receipts['dividers'] = ['capsule column 22', 'play-clock cell column 0']
    img = Image.fromarray(t.round().astype(np.uint8), 'RGBA')
    # The plate and the FLAG plate now span 948..986 (38 px, 15.76 HUD rows): their cells are area-filtered to 15
    # rows so no texel is minified (the SD footprint rule); the widths stay.
    for name in ('plate', 'flag'):
        x0, y0, x1, y1 = layout['cells'][name]['box']
        cell = img.crop((x0, y0, x1, y1))
        rows = texels(38, FY)
        pm = np.asarray(cell).astype(float); a = pm[..., 3:4] / 255
        pre = Image.fromarray(np.dstack([pm[..., :3] * a, pm[..., 3:]]).round().astype(np.uint8), 'RGBA').resize((x1 - x0, rows), Image.Resampling.BOX)
        q = np.asarray(pre).astype(float); qa = q[..., 3:4] / 255
        out = Image.fromarray(np.dstack([np.where(qa > 0, q[..., :3] / np.maximum(qa, 1e-6), 0), q[..., 3:]]).clip(0, 255).round().astype(np.uint8), 'RGBA')
        img.paste(Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0)), (x0, y0)); img.paste(out, (x0, y0))
        layout['cells'][name]['box'] = [x0, y0, x1, y0 + rows]
        receipts.setdefault('plate_rows', {})[name] = [y1 - y0, rows]
    used = [tuple(v['box']) for n2, v in layout['cells'].items() if n2 not in cells]
    for name, cell in cells.items():
        x, y = PLACE[name]; box = [x, y, x + cell.width, y + cell.height]
        assert not any(max(box[0], b[0]) < min(box[2], b[2]) and max(box[1], b[1]) < min(box[3], b[3]) for b in used), name
        img.paste(Image.new('RGBA', cell.size, (0, 0, 0, 0)), (x, y)); img.paste(cell, (x, y))
        layout['cells'][name] = {'box': box}; used.append(tuple(box))
        receipts[name]['cell'] = box
    label = layout['glyph_sets']['label']['glyphs']
    ex0, ey0, ex1, ey1 = receipts['espn_plate_mark']['ink_box']       # the down field's anchor top is y 950
    label['ESPN'] = {'cell': 'espn_plate_mark', 'size': [ex1 - ex0, ey1 - ey0], 'advance': ex1 - ex0, 'raise': 950 - ey0}
    w = receipts['label_Down']['glyph_width']
    h = round(receipts['label_Down']['tv_ink_height'] * 30 / 23, 3)   # 23 px of label ink on air draw 30 px tall here
    label['Down'] = {'cell': 'label_Down', 'size': [w, h], 'advance': round(w + 2, 3), 'raise': 0}
    # Glyph metrics stay under the loader's 256 px bound at half scale; the field's size 43 doubles them.
    layout['glyph_sets']['timeout_tab'] = {'cap_height': 21, 'glyphs': {'T': {'cell': 'timeout_tab', 'size': [172, 21], 'advance': 172, 'raise': 0}}}
    fields = {r['name']: r for r in layout['fields']}
    fields['clock']['strip_minute'] = True
    if 'timeout_tab' not in fields:
        layout['fields'].append({'name': 'timeout_tab', 'source': 'timeout tab', 'box': [458, 900, 802, 942], 'glyph_set': 'timeout_tab',
                                 'slots': 1, 'material': 9, 'colour': '#FFFFFF', 'alignment': 'center', 'anchor': [630.0, 900],
                                 'alt_anchor': [1291.0, 900], 'size': 42, 'z': -16})
    for row in layout['static']:
        if row['name'] == 'red':
            row['tint'] = 'play clock cell'
        if row['name'] == 'plate':
            # Noah on the candidate disc: the black ESPN plate "appears above the scorebug barely". On air the plate's
            # top edge is row 948, below the bar's rim glow (944..947), and it ends at 985 (Giants-Rams medians, both
            # plate states). Ours started at 945 and covered the glow, so the black plate read as a box over the rim.
            row['box'] = [822, 948, 1096, 986]
        if row['name'] == 'capsule':
            # The two capsule quads met edge to edge at x 1019: both edges fade to their transparent packing
            # gutters, so the black housing showed through as a third divider. The white capsule now runs one
            # texel under the play-clock cell, whose left edge blends over white.
            row['box'] = [839, 999, 1022, 1039]
    for row in layout['events']:
        row['box'] = [822, 948, 1096, 986]                               # the event plates keep the plate's footprint
    layout['provenance']['sb'] = {
        'job': 'b76-sb 2026-09-24', 'method': 'temporal medians of read-only broadcast frames, area-filtered to the 16:9 HUD footprint; no generated art',
        'sources': {'espn_plate_mark': '2026 MNF Giants at Rams off-air frames with the black ESPN plate',
                    'label_Down': '2026 MNF Broncos at Chiefs, every settled "3rd Down" second',
                    'timeout_tab': '2026 MNF Broncos at Chiefs, the two away TIMEOUT popups (3914..3915, 7055..7058)',
                    'flag': '2026 MNF Giants at Rams, every FLAG frame', 'dividers': 'removed; ESPN capsule has none'}}
    img.save(FOLDER / 'template.png')
    (FOLDER / 'layout.json').write_text(json.dumps(layout, indent=1) + '\n', newline='\n')
    Path(__file__).with_name('author_receipts.json').write_text(json.dumps(receipts, indent=1) + '\n', newline='\n')
    print(json.dumps(receipts, indent=1))


if __name__ == '__main__':
    main()
