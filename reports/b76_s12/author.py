"""Targeted b76-s12 art revision, measured from the 2026 Giants at Rams MNF broadcast.

This pass builds on reports/b72_s10/author.py (the same rounded-cell helper and
the same rule that every change follows a measurement) but it does not
regenerate the sheet. The s10 author rebuilds every cell from the immutable s9
baseline, which would revert beta 73's accents, glyph widths and logo fits and
beta 74.1's watermark cells. Here each selected step REPLACES one cell inside
the current template at its exact existing box, so the atlas stays 256 by 512,
the sheet 1536 by 512, all 91 cells keep their sizes, all 47 quads keep their
count and the appended payload keeps its size.

The script is idempotent: it always starts from the beta 75.1 bytes at
``--base`` (git) and applies only the selected steps, so any subset can be
re-authored and measured on its own. A file no step touches is written back
byte for byte.

Steps, in the order they were measured. Every trial, accepted or not, is in
reports/b76_s12/AUTHOR_STEPS.json with its full parameters and residuals on the
s10/s11 metric (reports/b76_s12/player_scale.py) and on the s11 guard.

Accepted (the default ``--steps``):
marks    The Giants and Rams source marks were one flat team-primary tone, so on a
         wing tinted with the same primary they nearly vanished. On air the Giants
         "ny" is white with a red keyline and the Rams "LA" is gold. Both are
         recoloured with sourced colours from team_colors_official_2026.json
         (Giants White #FFFFFF and Red #A71930, Rams Sol #FFD100). The letterforms
         are the existing silhouettes; the Giants keyline is the silhouette's own
         one-texel boundary band (the fill is the silhouette eroded by one texel),
         so the mark's outline is exactly the source outline, not a drawn one.
fits     Per-team logo fits so the rendered marks cover the measured broadcast
         boxes (layout.json logo_fit and team_accents.json logo_fit stay equal).
wing     The shared wing coverage cell, refit to the broadcast's measured coverage
         field: a strong outer edge band, a top glow that runs the whole wing and a
         thin bottom band, with the middle of the logo well darker than before.
housing  The clock housing: a light ring above and beside the white pill, a dark
         inner ring and a near-black band at the pill edge, at the measured box.
tray     The body darkens from 37 to 24 around the plate and housing, as measured.

Measured and rejected (kept selectable for the record):
plate    Flatter, brighter plate rows (with or without a lip and a bottom line).
bevel    Neutral bottom rim line and a top-only team glow instead of the s10 rows.

No broadcast pixel is copied: every cell is synthesized from measured numbers.
Team colours are never changed here; tints stay the sourced palette values.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
BASE = '3dd4087d5'
SPRITE = 'data/nfl2k5_scorebug_sprite'
LOGOS = 'data/nfl2k5_scorebug_mnf/logos'
FILES = (SPRITE + '/template.png', SPRITE + '/layout.json', SPRITE + '/team_accents.json',
         LOGOS + '/nyg.png', LOGOS + '/lar.png')
STEPS = ('marks', 'fits', 'wing', 'plate', 'housing', 'tray', 'bevel')
# The steps kept after measurement; plate and bevel were measured and rejected.
ACCEPTED = ('marks', 'fits', 'wing', 'housing', 'tray')

# Sourced colours (team_colors_official_2026.json): Giants White (tertiary) and
# Red (secondary), Rams Sol (secondary). Measured on air: white fill 248,248,248
# with a 161,47,65 keyline around it; gold 255,213,58. The inside keyline beat the
# outside one on the s10/s11 logo residual (1233.5 against 1723.0 player px).
MARKS = {'nyg': dict(fill='#FFFFFF', keyline='#A71930', keyline_texels=1, keyline_mode='inside'),
         'lar': dict(fill='#FFD100')}
# Filled by the fit search (reports/b76_s12/AUTHOR_STEPS.json). Broadcast boxes:
# Giants white 464..631 x 945..1048 with keyline 462..636 x 944..1048; Rams gold
# 1283..1462 x 944..1048 (record strips excluded, reports/b76_s12/harvest.json).
# Chosen: rendered Giants box 462..635 x 944..1049 (keyline) and 466..631 x 946..1046
# (white); Rams 1284..1460 x 944..1049. Height 61 of the 64 texels (zoom 0.953)
# keeps the one-texel transparent border; shifts are whole texels (1/64).
FITS = {'NYG': dict(fill_x=1.14, height=1.0, zoom=0.953, shift_x=-0.0156, shift_y=0.0),
        'LAR': dict(fill_x=1.10, height=1.0, zoom=0.953, shift_x=0.0469, shift_y=0.0)}
# Joint least-squares fit of three exponential terms to the broadcast's wing
# coverage (blue minus red, normalized by its 99.5th percentile), both wings and
# both sources, marks and record strips masked. X is the distance in source
# pixels from the bar's outer end, Y the row inside the 110-row bar.
WING = dict(a1=0.8761, d1=41.19, v1=0.2879, a2=0.60, d2=13.82, d3=461.6, a3=1.5, d4=2.839, d5=83.55,
            gamma=1.0, floor=0.0)
PLATE = dict(rows=[0, 1, 2, 3, 13, 14, 15, 16], values=[240, 255, 250, 248, 248, 246, 255, 215])
HOUSING = dict(box=[829, 990, 1090, 1046], ring_width=3, dark_width=3, ring=97, ring_bottom=70, ring_side=50,
               inner=30, fill=8)
# The s10 body bevel rows (reports/b72_s10/author.py), kept by the tray step.
S10_ROWS = dict(top_rows=[0, 2, 4, 7], top_values=[58, 145, 74, 37],
                bottom_rows=[103, 106, 108, 109], bottom_values=[37, 62, 108, 25])
# Measured centre tray: the body is about 37 at x 700 and 1180 and darkens to
# 24 to 27 around the plate and the clock housing (x 812 to 830 and 1090 to 1100).
TRAY = dict(tray=24, tray_inner=[830, 1090], tray_outer=[760, 1160])
# Rejected candidate (kept for the record): the broadcast's neutral bottom line
# and a top-only team glow. See AUTHOR_STEPS.json for its measured cost.
BEVEL = dict(top_rows=[0, 2, 4, 7], top_values=[58, 145, 74, 37],
             bottom_rows=[103, 104, 105, 106, 107, 108, 109], bottom_values=[37, 37, 45, 70, 100, 95, 35],
             rim_amplitude=0.68, rim_decay=2.0, rim_start=0, rim_tail=0.22, rim_bottom=False)


def git_bytes(rel, base=BASE):
    return subprocess.check_output(['git', 'show', base + ':' + rel], cwd=ROOT)


def png_image(data):
    return Image.open(io.BytesIO(data)).convert('RGBA')


def rounded(w, h, r, colour, ends='both'):
    """The s10 author's helper, unchanged."""
    im = Image.new('RGBA', (w * 4, h * 4), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w * 4 - 1, h * 4 - 1), r * 4, fill=colour)
    if ends == 'left':
        d.rectangle((w * 2, 0, w * 4 - 1, h * 4 - 1), fill=colour)
    if ends == 'right':
        d.rectangle((0, 0, w * 2, h * 4 - 1), fill=colour)
    return im.resize((w, h), Image.Resampling.LANCZOS)


def hexrgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


# ---------------------------------------------------------------- marks
def recolour_mark(image, fill, keyline=None, keyline_texels=1, keyline_mode='inside'):
    """Refill a mark; optionally give it a keyline derived from its own alpha.

    Straight RGBA in, straight RGBA out. The fill replaces every RGB value.
    ``inside``: the fill covers the silhouette eroded by ``keyline_texels``
    (3x3 min) and the keyline colour covers the remaining boundary band, so the
    mark's outer silhouette is exactly the source silhouette. ``outside``: the
    keyline is the silhouette dilated by ``keyline_texels`` (3x3 max) under the
    unchanged fill, so the mark grows by that band.
    """
    a = np.asarray(image.convert('RGBA')).astype(np.float64)
    alpha = a[..., 3] / 255.0
    # The runtime resampler drops alpha below 16/255 as Lanczos ringing; derive
    # the keyline from the same cleaned silhouette so faint tails are not outlined.
    clean = np.where(a[..., 3] < 16, 0.0, alpha)
    rgb = np.array(hexrgb(fill), dtype=np.float64)
    if keyline is None:
        out = a.copy()
        out[..., :3] = rgb
        out[..., 3] = a[..., 3]
        return Image.fromarray(np.rint(out).astype('uint8'), 'RGBA')

    def morph(field, op):
        for _ in range(keyline_texels):
            padded = np.pad(field, 1)
            field = op([padded[dy:dy + field.shape[0], dx:dx + field.shape[1]]
                        for dy in range(3) for dx in range(3)], axis=0)
        return field
    if keyline_mode == 'inside':
        top, under = morph(clean, np.min), clean
    elif keyline_mode == 'outside':
        top, under = clean, morph(clean, np.max)
    else:
        raise ValueError('keyline_mode must be inside or outside')
    red = np.array(hexrgb(keyline), dtype=np.float64)
    # The fill layer composited over the keyline layer (premultiplied source-over).
    out_alpha = top + under * (1 - top)
    premult = rgb[None, None] * top[..., None] + red[None, None] * (under * (1 - top))[..., None]
    straight = np.where(out_alpha[..., None] > 0, premult / np.maximum(out_alpha[..., None], 1e-9), red)
    out = np.dstack([straight, out_alpha * 255.0])
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype('uint8'), 'RGBA')


def mark_receipt(before, after, name, spec):
    b, a = np.asarray(before), np.asarray(after)
    ink_b, ink_a = b[..., 3] > 0, a[..., 3] > 0
    return dict(file=name, **spec, ink_pixels_before=int(ink_b.sum()), ink_pixels_after=int(ink_a.sum()),
                alpha_bbox_before=list(before.getchannel('A').getbbox()),
                alpha_bbox_after=list(after.getchannel('A').getbbox()),
                previous_median_rgb=[int(v) for v in np.median(b[b[..., 3] > 128][:, :3], axis=0)])


# ---------------------------------------------------------------- wing
def wing_cell(size, p):
    """Coverage field at the 340 x 110 source size, box-filtered into the cell."""
    y, x = np.mgrid[0:110, 0:340].astype(np.float64)
    edge = p['a1'] * np.exp(-x / p['d1']) * (1 - p['v1'] * y / 109)
    top = p['a2'] * np.exp(-y / p['d2']) * np.exp(-x / p['d3'])
    bottom = p['a3'] * np.exp(-(109 - y) / p['d4']) * np.exp(-x / p['d5'])
    cover = np.clip(edge + top + bottom, 0, 1)
    if p.get('gamma', 1.0) != 1.0:
        cover = cover ** p['gamma']
    cover = np.maximum(cover, p.get('floor', 0.0) * np.exp(-x / p['d1']))
    shape = np.asarray(rounded(340, 110, 8, 'white', 'left')).astype(np.float64)[..., 3] / 255.0
    v = np.zeros((110, 340, 4), dtype=np.float64)
    v[..., :3] = 255
    v[..., 3] = 255 * cover * shape
    im = Image.fromarray(np.rint(v).astype('uint8'), 'RGBA').resize(size, Image.Resampling.BOX)
    arr = np.asarray(im).copy()
    arr[..., :3] = 255
    # Monotonic fade to exactly zero at the inner end (sprite test contract).
    arr[:, -1, 3] = 0
    arr[..., 3] = np.minimum.accumulate(arr[..., 3], axis=1)
    return Image.fromarray(arr, 'RGBA')


# ---------------------------------------------------------------- plate
def plate_cell(base_cell, p):
    """Keep the s10 plate silhouette (its alpha); replace the row values."""
    arr = np.asarray(base_cell).copy()
    h = arr.shape[0]
    values = np.interp(np.arange(h), p['rows'], p['values'])
    arr[..., :3] = np.rint(values)[:, None, None]
    return Image.fromarray(arr, 'RGBA')


# ---------------------------------------------------------------- housing
def housing_cell(size, box, p):
    """Rounded housing at the measured outer box, drawn at 4x then box-filtered.

    Measured around the pill (frames 620 and 120, columns 880 and 960, rows 1019):
    from the outer edge inward a light ring about 3 px wide (luma about 97 on top,
    70 at the bottom, 46 to 54 at the sides), a dark ring about 3 px (about 30),
    then a near-black band that meets the pill edge.
    """
    w, h = box[2] - box[0], box[3] - box[1]
    s = 4
    W, H = w * s, h * s

    def mask(inset):
        m = Image.new('L', (W, H), 0)
        r = max(1, H // 2 - inset * s)
        ImageDraw.Draw(m).rounded_rectangle((inset * s, inset * s, W - 1 - inset * s, H - 1 - inset * s), r, fill=255)
        return np.asarray(m).astype(np.float64) / 255.0
    outer, mid, inner = mask(0), mask(p['ring_width']), mask(p['ring_width'] + p['dark_width'])
    yy = np.linspace(0, 1, H)[:, None]
    xx = np.abs(np.linspace(-1, 1, W))[None, :]
    level = p['ring'] * (1 - yy) + p['ring_bottom'] * yy
    side = np.clip((xx - 0.85) / 0.15, 0, 1)
    level = level * (1 - side) + p['ring_side'] * side
    value = level * (1 - mid) + p['inner'] * (mid - inner) + p['fill'] * inner
    arr = np.zeros((H, W, 4), dtype=np.float64)
    arr[..., :3] = value[..., None]
    arr[..., 3] = 255 * outer
    out = Image.fromarray(np.clip(np.rint(arr), 0, 255).astype('uint8'), 'RGBA')
    return out.resize(size, Image.Resampling.BOX)


# ---------------------------------------------------------------- bevel
def body_cell(size, rows_p, tray_p, bar=(437, 1478)):
    """Neutral bar body: bevel rows (s10 unless the bevel step supplies them) and the centre tray."""
    im = rounded(1041, 110, 8, (37, 37, 37, 255))
    v = np.asarray(im).astype(np.float64).copy()
    rows = np.interp(np.arange(110), rows_p['top_rows'] + rows_p['bottom_rows'],
                     rows_p['top_values'] + rows_p['bottom_values'])
    x = np.arange(bar[0], bar[1]) + 0.5
    lo, hi = tray_p['tray_inner']
    olo, ohi = tray_p['tray_outer']

    def smooth(t):
        t = np.clip(t, 0, 1)
        return t * t * (3 - 2 * t)
    # Smoothstep from the body level (37) at the outer points to the tray level
    # at the inner points, flat between the inner points. Bevel rows keep their values.
    weight = np.where(x < lo, smooth((x - olo) / (lo - olo)), np.where(x > hi, smooth((ohi - x) / (ohi - hi)), 1.0))
    body = rows[:, None] * np.ones((1, 1041))
    interior = np.abs(rows - 37) < 0.5
    tray = 37 + (tray_p['tray'] - 37) * weight
    body[interior] = tray[None, :]
    v[..., :3] = body[..., None]
    return Image.fromarray(np.clip(np.rint(v), 0, 255).astype('uint8'), 'RGBA').resize(size, Image.Resampling.BOX)


def rim_cell(size, name, p):
    """Team-tinted glow along the TOP edge only; the broadcast bottom rim is neutral.

    Measured at x 700, 790, 1120 and 1230: a dark edge row, then a team-blue glow
    that peaks two to four rows below the edge and fades into the body, strongest
    near the bar's outer ends and still present at the centre.
    """
    v = np.zeros((110, 523, 4), dtype=np.float64)
    v[:, :, :3] = 255
    ramp = np.linspace(1, p['rim_tail'], 523)
    y = np.arange(110, dtype=np.float64)
    start = p['rim_start']
    # rim_bottom keeps the s10 symmetric glow (top and bottom edges) for comparison.
    edge = np.minimum(y, 109 - y) if p.get('rim_bottom') else y
    glow = np.where(edge < start, 0.0, p['rim_amplitude'] * np.exp(-(edge - start) / p['rim_decay']))
    v[..., 3] = 255 * glow[:, None] * ramp[None, :]
    if name == 'home_rim':
        v = v[:, ::-1].copy()
    return Image.fromarray(np.clip(np.rint(v), 0, 255).astype('uint8'), 'RGBA').resize(size, Image.Resampling.BOX)


# ---------------------------------------------------------------- driver
def encode_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def author(steps, params, base=BASE):
    raw = {rel: git_bytes(rel, base) for rel in FILES}
    spec = json.loads(raw[SPRITE + '/layout.json'])
    accents = json.loads(raw[SPRITE + '/team_accents.json'])
    sheet = png_image(raw[SPRITE + '/template.png'])
    logos = {k: png_image(raw[LOGOS + '/' + k + '.png']) for k in ('nyg', 'lar')}
    cells = spec['cells']
    rows = {r['name']: r for r in spec['static']}
    receipts = dict(base=base, steps=list(steps))
    changed = set()

    def cell_size(name):
        box = cells[name]['box']
        return box[2] - box[0], box[3] - box[1]

    def replace(name, image):
        box = tuple(cells[name]['box'])
        if image.size != cell_size(name):
            raise ValueError('Cell %s must stay %sx%s to keep the atlas and payload fixed' % (name, *cell_size(name)))
        sheet.paste(image, box[:2])
        changed.add('template')

    if 'marks' in steps:
        receipts['marks'] = []
        for key, value in sorted(params['marks'].items()):
            before = logos[key]
            after = recolour_mark(before, value['fill'], value.get('keyline'), value.get('keyline_texels', 1),
                                  value.get('keyline_mode', 'inside'))
            receipts['marks'].append(mark_receipt(before, after, key + '.png', value))
            logos[key] = after
            changed.add(key)
    if 'fits' in steps:
        receipts['fits'] = {}
        for team, fit in sorted(params['fits'].items()):
            fit = {k: round(float(v), 4) for k, v in fit.items()}
            receipts['fits'][team] = dict(before=spec['logo_fit']['by_team'][team], after=fit)
            spec['logo_fit']['by_team'][team] = fit
            accents['teams'][team]['logo_fit'] = fit
            changed.update({'layout', 'accents'})
    if 'wing' in steps:
        image = wing_cell(cell_size('wing'), params['wing'])
        replace('wing', image)
        replace('home_wing', image)
        receipts['wing'] = dict(params['wing'])
    if 'plate' in steps:
        box = cells['plate']['box']
        replace('plate', plate_cell(sheet.crop(tuple(box)), params['plate']))
        receipts['plate'] = dict(params['plate'])
    if 'housing' in steps:
        hp = params['housing']
        replace('housing', housing_cell(cell_size('housing'), hp['box'], hp))
        receipts['housing'] = dict(previous_box=list(rows['housing']['box']), **hp)
        rows['housing']['box'] = list(hp['box'])
        changed.add('layout')
    if 'tray' in steps or 'bevel' in steps:
        rows_p = params['bevel'] if 'bevel' in steps else S10_ROWS
        tray_p = params['tray'] if 'tray' in steps else dict(TRAY, tray=37)
        replace('body', body_cell(cell_size('body'), rows_p, tray_p))
        if 'tray' in steps:
            receipts['tray'] = dict(tray_p)
    if 'bevel' in steps:
        bp = params['bevel']
        for name in ('away_rim', 'home_rim'):
            replace(name, rim_cell(cell_size(name), name, bp))
        receipts['bevel'] = dict(bp)
    if steps:
        prov = spec['provenance']
        prov.update(
            author='reports/b76_s12/author.py', revision='b76-s12',
            fidelity_report='reports/b76_s12/AUTHOR_STEPS.json',
            geometry_steps=list(steps),
            measured_from='2026 Giants at Rams Monday Night Football, reports/b76_s12/harvest.json',
            base_author='reports/b72_s10/author.py (cells replaced in place, not regenerated)')
        if 'wing' in steps:
            # The s10 single decay constant no longer describes the wing cell.
            prov.pop('wing_decay', None)
            prov['wing_model'] = dict(form='a1*exp(-x/d1)*(1-v1*y/109) + a2*exp(-y/d2)*exp(-x/d3) '
                                           '+ a3*exp(-(109-y)/d4)*exp(-x/d5), clipped to 1',
                                      **{k: params['wing'][k] for k in ('a1', 'd1', 'v1', 'a2', 'd2', 'd3',
                                                                          'a3', 'd4', 'd5')})
        changed.add('layout')
    outputs = {}
    outputs[SPRITE + '/template.png'] = encode_png(sheet) if 'template' in changed else raw[SPRITE + '/template.png']
    outputs[SPRITE + '/layout.json'] = ((json.dumps(spec, indent=1) + '\n').encode('utf-8')
                                        if 'layout' in changed else raw[SPRITE + '/layout.json'])
    outputs[SPRITE + '/team_accents.json'] = ((json.dumps(accents, indent=2) + '\n').encode('utf-8')
                                              if 'accents' in changed else raw[SPRITE + '/team_accents.json'])
    for key in ('nyg', 'lar'):
        rel = LOGOS + '/' + key + '.png'
        outputs[rel] = encode_png(logos[key]) if key in changed else raw[rel]
    receipts['outputs'] = {rel: dict(sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                                     changed=data != raw[rel]) for rel, data in outputs.items()}
    return outputs, receipts


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--steps', default=','.join(ACCEPTED), help='Comma list from: ' + ', '.join(STEPS) + ' (default: the accepted steps)')
    p.add_argument('--params', type=Path, help='JSON overriding any of marks/fits/wing/plate/housing/tray/bevel')
    p.add_argument('--base', default=BASE)
    p.add_argument('--receipts', type=Path, default=OUT / 'author_receipts.json')
    a = p.parse_args(argv)
    steps = [s for s in a.steps.split(',') if s]
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        raise SystemExit('Unknown step(s): ' + ', '.join(unknown))
    steps = [s for s in STEPS if s in steps]
    params = dict(marks=MARKS, fits=FITS, wing=WING, plate=PLATE, housing=HOUSING, tray=TRAY, bevel=BEVEL)
    if a.params:
        override = json.loads(a.params.read_text(encoding='utf-8'))
        for key, value in override.items():
            if key not in params:
                raise SystemExit('Unknown parameter group ' + key)
            params[key] = ({**params[key], **value} if key not in ('marks', 'fits') else value)
    outputs, receipts = author(steps, params, a.base)
    for rel, data in outputs.items():
        (ROOT / rel).write_bytes(data)
    receipts['params'] = params
    a.receipts.write_text(json.dumps(receipts, indent=2) + '\n', encoding='utf-8', newline='\n')
    print('Authored steps:', steps or 'none (base bytes restored)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
