"""Beta 76 sbfix: the down plate's "Inches" and the quarter pill's overtime in the bar's own capitals (idempotent).

In game (km2 lab 1, frame game-0265s) the plate read "3rd & 1nCh6s". The retail down formatter FC7D0 prints
"%s & %s" with the literal "Inches" (0xE6C418) when the distance rounds to nothing; the sprite runtime draws it as
the tokens 'Inch' + 'es', and those two cells were beta 72's reconstructions for a word no broadcast had shown
(reports/b72_s9/art_provenance.json: I from the numeral 1, c and e cut from the numeral 0). The quarter formatter
FC090 prints "OT%d" in overtime: 'OT1' drew "0T" (the numeral 0 and a small T), and OT2 onward had no token, so the
pill went blank.

The 2026 ESPN bar never prints a lowercase word distance. Over the full Broncos at Chiefs broadcast (8,657 labelled
seconds, grammar/labels.jsonl) its only word distance is GOAL, always in capitals (398 s: 1st 107, 2nd 171, 3rd 62,
4th 58), and short yardage reads "& 1" (no Inches plate in the game). So "Inches" draws as INCHES in the capitals the
plate already uses for GOAL, and every overtime period as OT. The tokens stay the retail text: no XBE byte changes.

Every letter comes from the traced broadcast masks already in the repository (reports/b72_s9/glyphs, contours at
4x); nothing is generated and no font file is read:
  I       the stem of GOAL's L (15 px wide at 4x on the 88-row flat cap);
  N H S   the quarter pill's traced capitals (12 px on air) scaled 88/48 to the plate's flat cap; their stems land
          at 14.7 px against the L's 15;
  C       GOAL's G: its upper half and that half mirrored (both terminals, no bar);
  E       GOAL's L, its arm mirrored to the top (95 % long) and a middle arm (86 %) centred on the cap;
  O T     (overtime) GOAL's O at the pill numerals' 18 px, and the traced quarter T at the same height.
Cells are area-filtered at the field's current native footprint: the metrics use a 30 px design grid,
while sb2's 24 px field needs nine texel rows and a 0.8 coverage exponent. Across, 1/3 texel per display px
(16:9) prevents minification; the field tints the white coverage. The widest plate the formatter
can print, "2nd & INCHES", must fit the down field without the runtime's field compression (a compressed field would
minify every label glyph, which the SD rule forbids): the word takes GOAL's letter gaps a little tighter and is
condensed horizontally by the factor that fits, the offline equivalent of a broadcast engine's auto-fit.

Usage: python3 reports/b76_sbfix/author.py [--check]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
MASKS = ROOT / 'reports/b72_s9'
RECEIPTS = Path(__file__).with_name('author_receipts.json')
FX, FY = 1 / 3, 448 / 1080          # texels per layout px (16:9 after the 27/32 contraction; the 448-line viewport)
LABEL_K = 30 / 23                   # design-grid px per px of on-air label ink; the field applies its own scale
QUARTER_K = 22 / 18                 # layout px per px of on-air pill ink (the 18 px numerals draw 22 px tall)
FLAT = 88                           # GOAL's flat cap at 4x: rows 4..91 of the 92-row mask (O and G overshoot to row 0)
SPACING = dict(straight=16, round=14, es=12)                   # 4x gaps, a little under GOAL's own (G-O 19, A-L 18)
MARGIN = 1.0                        # layout px left free in the down field by the widest plate
TOKEN_GAP = SPACING['straight']     # 'Inch' ends on H and 'es' starts on E: the same straight-straight gap
PLACE = {'label_Inch': (100, 300), 'label_es': (136, 300), 'quarter_OT': (155, 300)}
# The beta-72 cells these replace (cleared on the first run; later runs find the new boxes).
LEGACY = {'label_Inch': [587, 47, 613, 59], 'label_es': [615, 47, 629, 59], 'quarter_OT': [699, 47, 709, 56]}
OVERTIME = ('OT', 'OT1', 'OT2', 'OT3', 'OT4', 'OT5', 'OT6', 'OT7', 'OT8', 'OT9')   # FC090 prints "OT%d" (quarter - 4)


ORDINALS = ('1st', '2nd', '3rd', '4th')                        # FC7D0's downs


def _tokens(text, glyphs):
    """The sprite runtime's match: the first token in table order ((-len, token), as compiled) the text starts with."""
    order = sorted(glyphs, key=lambda t: (-len(t), t))
    out, at = [], 0
    while at < len(text):
        token = next(t for t in order if text.startswith(t, at))
        out.append(token)
        at += len(token)
    return out


def texels(px, per):
    """Largest whole texel count that never exceeds the footprint (one mip, no minification)."""
    return max(1, int(px * per + 0.02))


def _mask(name):
    rows = json.loads((MASKS / 'harvest.json').read_text())['glyphs']
    return np.asarray(Image.open(MASKS / 'glyphs' / rows[name]['file']).convert('L')).astype(float) / 255


def _resize(a, size):
    return np.asarray(Image.fromarray(np.round(a * 255).astype(np.uint8)).resize(size, Image.Resampling.LANCZOS)).astype(float) / 255


def _flat(a):
    """A flat-topped letter on the 92-row box: rows 4..91, the baseline on row 91."""
    out = np.zeros((92, a.shape[1]))
    out[92 - FLAT:] = a[:FLAT]
    return out


def letters():
    goal = _mask('label_GOAL')                                   # 92 x 332: G 0..76, O 95..173, A 184..258, L 276..331
    assert goal.shape == (92, 332), goal.shape
    ell = goal[:, 276:332]
    i = goal[:, 276:291].copy()                                  # the L's stem
    e = np.maximum(ell, np.vstack([np.zeros((92 - FLAT, ell.shape[1])), ell[92 - FLAT:][::-1]]))
    arm = ell[76:92, 15:]                                        # the arm beyond the stem, 16 rows
    mid = (4 + 91) // 2 - 8
    e[mid:mid + 16, 15:15 + round(arm.shape[1] * 0.86)] = np.maximum(e[mid:mid + 16, 15:15 + round(arm.shape[1] * 0.86)],
                                                                     arm[:, :round(arm.shape[1] * 0.86)])
    e[92 - FLAT:92 - FLAT + 16, 15 + round(arm.shape[1] * 0.95):] = 0
    g = goal[:, 0:77]
    c = g.copy()
    c[46:] = g[:46][::-1]                                        # the G's upper half and its mirror
    quarter = {k: _mask('quarter_' + k) for k in 'NHST'}
    scaled = {k: _flat(_resize(v, (round(v.shape[1] * FLAT / v.shape[0]), FLAT))) for k, v in quarter.items() if k != 'T'}
    o = goal[:, 95:174]
    o18 = _resize(o, (round(o.shape[1] * 72 / 92), 72))
    t18 = _resize(quarter['T'], (round(quarter['T'].shape[1] * 72 / quarter['T'].shape[0]), 72))
    return dict(I=i, N=scaled['N'], C=c, H=scaled['H'], E=e, S=scaled['S'], O=o18, T=t18)


def word(parts):
    width = sum(p.shape[1] for p, _ in parts) + sum(gap for _, gap in parts[:-1])
    out = np.zeros((parts[0][0].shape[0], width))
    x = 0
    for p, gap in parts:
        out[:, x:x + p.shape[1]] = np.maximum(out[:, x:x + p.shape[1]], p)
        x += p.shape[1] + gap
    return out


def _cell(alpha, size):
    """Area-filter white coverage to `size` texels (premultiplied while filtering), as reports/b76_sb does."""
    a = np.clip(alpha, 0, 1)
    pm = np.dstack([np.full(a.shape + (3,), 255.0) * a[..., None], a * 255])
    im = Image.fromarray(np.clip(pm, 0, 255).astype(np.uint8), 'RGBA').resize(size, Image.Resampling.BOX)
    p = np.asarray(im).astype(float)
    al = p[..., 3:4] / 255
    col = np.where(al > 0, p[..., :3] / np.maximum(al, 1e-6), 255)
    return Image.fromarray(np.dstack([np.clip(col, 0, 255), p[..., 3]]).round().astype(np.uint8), 'RGBA')


def build(layout, template):
    """Return the new (layout, template, receipts) for the current folder contents; the inputs are not modified."""
    layout = json.loads(json.dumps(layout))
    image = template.copy()
    lt = letters()
    s, r = SPACING['straight'], SPACING['round']
    masks = {'label_Inch': word([(lt['I'], s), (lt['N'], r), (lt['C'], r), (lt['H'], 0)]),
             'label_es': word([(lt['E'], SPACING['es']), (lt['S'], 0)]),
             'quarter_OT': word([(lt['O'], 12), (lt['T'], 0)])}
    # The widest prefix the formatter prints before the distance ("2nd & ") and the room the down field leaves after it.
    label = layout['glyph_sets']['label']
    field = next(f for f in layout['fields'] if f['name'] == 'down')
    room = (field['box'][2] - field['box'][0]) / (field['size'] / label['cap_height'])
    prefix = max(sum(label['glyphs'][t]['advance'] for t in _tokens(f'{o} & ', label['glyphs'])) for o in ORDINALS)
    natural = (masks['label_Inch'].shape[1] + TOKEN_GAP + masks['label_es'].shape[1]) / 4 * LABEL_K
    condense = min(1.0, (room - prefix - MARGIN) / natural)
    receipts = dict(fit=dict(field_width=room, widest_prefix=round(prefix, 3), natural_word=round(natural, 3),
                             condense=round(condense, 4), widest_plate=round(prefix + natural * condense, 3)))
    glyph_w = {}
    cells = {}
    for name, m in masks.items():
        k, rows = (QUARTER_K, 22) if name == 'quarter_OT' else (LABEL_K * condense, 30)
        width = m.shape[1] / 4 * k
        glyph_w[name] = round(width, 3)
        # sb2: glyph metrics keep their design grid; texels follow the current field's native footprint.
        field_scale = 1.0 if name == 'quarter_OT' else field['size'] / label['cap_height']
        cells[name] = _cell(m, (texels(width * field_scale, FX), texels(rows * field_scale, FY)))
        if name != 'quarter_OT' and field_scale < 1:
            alpha = np.asarray(cells[name].getchannel('A')) / 255.0
            cells[name].putalpha(Image.fromarray(np.rint(alpha ** .8 * 255).astype('uint8')))
        receipts[name] = dict(ink_px=[m.shape[1] / 4, m.shape[0] / 4], glyph_size=[glyph_w[name], rows], texels=list(cells[name].size))
    others = [tuple(v['box']) for n, v in layout['cells'].items() if n not in cells]

    def overlaps(box):
        return any(max(box[0], b[0]) < min(box[2], b[2]) and max(box[1], b[1]) < min(box[3], b[3]) for b in others)
    for name, cell in cells.items():
        # Clear the replaced cell (the beta-72 box on the first run, this pass's box after it), never another cell's pixels.
        for box in sorted({tuple(LEGACY[name]), tuple(layout['cells'][name]['box'])}):
            if not overlaps(box):
                image.paste(Image.new('RGBA', (box[2] - box[0], box[3] - box[1]), (0, 0, 0, 0)), box[:2])
        x, y = PLACE[name]
        box = [x, y, x + cell.width, y + cell.height]
        assert not overlaps(box), name
        image.paste(cell, (x, y))
        layout['cells'][name] = {'box': box}
        others.append(tuple(box))
        receipts[name].update(cell=box, sha256=hashlib.sha256(cell.tobytes()).hexdigest())
    label = layout['glyph_sets']['label']['glyphs']
    gap = round(TOKEN_GAP / 4 * LABEL_K * condense, 3)
    label['Inch'] = {'cell': 'label_Inch', 'size': [glyph_w['label_Inch'], 30], 'advance': round(glyph_w['label_Inch'] + gap, 3), 'raise': 0}
    label['es'] = {'cell': 'label_es', 'size': [glyph_w['label_es'], 30], 'advance': round(glyph_w['label_es'] + 2, 3), 'raise': 0}
    quarter = layout['glyph_sets']['quarter']['glyphs']
    for token in OVERTIME:
        quarter[token] = {'cell': 'quarter_OT', 'size': [glyph_w['quarter_OT'], 22], 'advance': round(glyph_w['quarter_OT'] + 2, 3)}
    layout['provenance']['sbfix'] = {
        'job': 'b76-sbfix 2026-09-25',
        'method': 'capitals assembled from the traced broadcast masks in reports/b72_s9/glyphs (I, E from GOAL\'s L; C from '
                  'GOAL\'s G mirrored; N, H, S, T the pill\'s traced capitals scaled to the cap; O GOAL\'s O); no generated art',
        'why': 'the 2026 ESPN bar writes its only word distance in capitals (GOAL, 398 s of the full Broncos at Chiefs game) and '
               'never showed an Inches plate; the retail "Inches" and "OT%d" draw as INCHES and OT',
        'cells': {n: receipts[n]['cell'] for n in cells}}
    receipts['tokens'] = dict(label={'Inch': label['Inch'], 'es': label['es']}, quarter={t: quarter[t] for t in OVERTIME})
    return layout, image, receipts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='Rebuild in memory and report whether the folder matches; write nothing')
    a = ap.parse_args(argv)
    layout = json.loads((FOLDER / 'layout.json').read_text(encoding='utf-8'))
    template = Image.open(FOLDER / 'template.png').convert('RGBA')
    new_layout, new_image, receipts = build(layout, template)
    same = new_layout == layout and new_image.tobytes() == template.tobytes()
    if a.check:
        print(json.dumps(dict(current=same), indent=1))
        return 0 if same else 1
    new_image.save(FOLDER / 'template.png')
    (FOLDER / 'layout.json').write_text(json.dumps(new_layout, indent=1) + '\n', encoding='utf-8', newline='\n')
    RECEIPTS.write_text(json.dumps(receipts, indent=1, sort_keys=True) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(receipts, indent=1, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
