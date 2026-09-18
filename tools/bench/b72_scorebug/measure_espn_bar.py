#!/usr/bin/env python3
"""Measure the ESPN 2026 bar on frame_012001 and the same features on the sprite render.

  python3 measure_espn_bar.py <preview_dir> <stem>     # prints JSON
All ESPN numbers are 1920x1080 source pixels; sprite numbers are converted back to
source pixels through the preview JSON's display.quads mapping, so the two compare.
"""
import json, sys
from pathlib import Path
from PIL import Image
import numpy as np


def J(o):
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return round(float(o), 2)
    raise TypeError(repr(o))

FRAME = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
prev, stem = Path(sys.argv[1]), sys.argv[2]
a = np.asarray(Image.open(FRAME).convert('RGB'), dtype=float)
out = {'espn': {}}
E = out['espn']

# body: vertical luminance profile through a clean charcoal column (x=1150, clear of ink)
col = a[942:1053, 1230]
E['body_row_profile_x1230'] = [[i + 942, [round(v, 1) for v in col[i]]] for i in range(0, 111, 5)]
E['body_flat_rgb_mid'] = [round(v, 1) for v in a[995:1040, 1215:1250].reshape(-1, 3).mean(0)]
E['body_top_rim_rgb'] = [round(v, 1) for v in a[942:944, 700:820].reshape(-1, 3).mean(0)]
E['body_top_glow_rgb_y946'] = [round(v, 1) for v in a[946:948, 700:820].reshape(-1, 3).mean(0)]
E['body_bottom_rim_rgb'] = [round(v, 1) for v in a[1050:1052, 700:820].reshape(-1, 3).mean(0)]

# away wing ramp: horizontal profile at a row clear of the logo
row = a[1046, 437:660]
E['away_wing_profile_y1046'] = [[437 + i, [round(v, 1) for v in row[i]]] for i in range(0, 223, 10)]
lum = row.mean(-1)
half = np.where(lum <= (lum[0] + lum[-1]) / 2)[0]
E['away_wing_half_fade_x'] = int(437 + half[0]) if len(half) else None
E['away_wing_outer_rgb'] = [round(v, 1) for v in a[1040:1050, 438:446].reshape(-1, 3).mean(0)]
row = a[1046, 1265:1479]
E['home_wing_outer_rgb'] = [round(v, 1) for v in a[1040:1050, 1470:1477].reshape(-1, 3).mean(0)]
lum = row.mean(-1)
half = np.where(lum >= (lum[0] + lum[-1]) / 2)[0]
E['home_wing_half_fade_x'] = int(1265 + half[0]) if len(half) else None

# plate: vertical gradient through a clean column, and the top lip
E['plate_column_x870'] = [[y, [round(v, 1) for v in a[y, 870]]] for y in range(945, 990, 3)]
E['plate_top_rgb'] = [round(v, 1) for v in a[948:951, 850:1070].reshape(-1, 3).mean(0)]
E['plate_bottom_rgb'] = [round(v, 1) for v in a[978:982, 850:1070].reshape(-1, 3).mean(0)]
E['pointer_box'] = [951, 942, 965, 947]
E['pointer_rgb'] = [round(v, 1) for v in a[943:946, 953:963].reshape(-1, 3).mean(0)]

# capsule and red cell
E['capsule_rgb'] = [round(v, 1) for v in a[1015:1025, 900:915].reshape(-1, 3).mean(0)]
E['red_cell_rgb'] = [round(v, 1) for v in a[1010:1030, 1060:1078].reshape(-1, 3).mean(0)]
E['housing_rgb'] = [round(v, 1) for v in a[1041:1044, 860:1060].reshape(-1, 3).mean(0)]
E['housing_side_rgb'] = [round(v, 1) for v in a[1005:1035, 840:848].reshape(-1, 3).mean(0)]
# separator ticks inside the white capsule: columns darker than the capsule
strip = a[1005:1035, 839:1019].mean(-1)
colmin = strip.min(0)
ticks = [839 + i for i in range(len(colmin)) if colmin[i] < strip.max() - 25]
groups = []
for x in ticks:
    if groups and x - groups[-1][-1] <= 2:
        groups[-1].append(x)
    else:
        groups.append([x])
E['capsule_dark_column_groups'] = [[g[0], g[-1]] for g in groups]

# logos: bounding box of non-charcoal pixels inside each wing
for name, box in (('away_logo', (440, 943, 660, 1051)), ('home_logo', (1258, 943, 1478, 1051))):
    sub = a[box[1]:box[3], box[0]:box[2]]
    lum = sub.mean(-1)
    sat = sub.max(-1) - sub.min(-1)
    mask = (lum > 150) | (sat > 70)
    rows = np.where(mask.any(1))[0]; cols = np.where(mask.any(0))[0]
    E[name + '_ink_box'] = [int(box[0] + cols.min()), int(box[1] + rows.min()),
                            int(box[0] + cols.max()), int(box[1] + rows.max())]
    E[name + '_ink_size'] = [int(cols.max() - cols.min() + 1), int(rows.max() - rows.min() + 1)]

# scores and ticks
for name, box in (('away_score', (700, 960, 815, 1022)), ('home_score', (1105, 960, 1220, 1022))):
    sub = a[box[1]:box[3], box[0]:box[2]].mean(-1)
    mask = sub > 175
    rows = np.where(mask.any(1))[0]; cols = np.where(mask.any(0))[0]
    E[name + '_ink_box'] = [int(box[0] + cols.min()), int(box[1] + rows.min()),
                            int(box[0] + cols.max()), int(box[1] + rows.max())]
_s = a[975:1010, 736:776].reshape(-1, 3)
E['score_rgb_p90'] = [round(v, 1) for v in np.percentile(_s, 90, axis=0)]
E['score_rgb_max'] = [round(v, 1) for v in _s.max(0)]
sub = a[1028:1042, 700:820].mean(-1)
mask = sub > 190
cols = np.where(mask.any(0))[0]; rows = np.where(mask.any(1))[0]
runs = []
prev_c = None
for c in cols:
    if prev_c is None or c - prev_c > 1:
        runs.append([c, c])
    else:
        runs[-1][1] = c
    prev_c = c
E['away_tick_runs_source_x'] = [[700 + r[0], 700 + r[1]] for r in runs]
E['tick_rows_source_y'] = [int(1028 + rows.min()), int(1028 + rows.max())]

# ---- the same features on the sprite render, mapped back to source pixels
out['sprite'] = {}
for aspect in ('43', '169'):
    meta = json.loads((prev / f'{stem}_{aspect}.json').read_text())
    disp = meta['display']
    im = np.asarray(Image.open(disp['path']).convert('RGB'), dtype=float)
    q = disp['quads']
    # affine from source x to display x, from the two body end quads
    sx = (q['body_right'][2] - q['body_left'][0]) / (1478 - 437)
    ox = q['body_left'][0] - 437 * sx
    sy = (q['body_left'][3] - q['body_left'][1]) / (1052 - 942)
    oy = q['body_left'][1] - 942 * sy
    X = lambda v: int(round(v * sx + ox))
    Y = lambda v: int(round(v * sy + oy))
    rec = {'display': disp['aspect'], 'source_to_display_scale': [round(sx, 4), round(sy, 4)]}
    rec['body_flat_rgb_mid'] = [round(v, 1) for v in im[Y(995):Y(1040), X(1215):X(1250)].reshape(-1, 3).mean(0)]
    rec['body_top_rim_rgb'] = [round(v, 1) for v in im[Y(942):Y(944), X(700):X(820)].reshape(-1, 3).mean(0)]
    rec['body_top_glow_rgb_y946'] = [round(v, 1) for v in im[Y(946):Y(948), X(700):X(820)].reshape(-1, 3).mean(0)]
    rec['body_bottom_rim_rgb'] = [round(v, 1) for v in im[Y(1050):Y(1052), X(700):X(820)].reshape(-1, 3).mean(0)]
    rec['away_wing_outer_rgb'] = [round(v, 1) for v in im[Y(1040):Y(1050), X(438):X(446)].reshape(-1, 3).mean(0)]
    rec['home_wing_outer_rgb'] = [round(v, 1) for v in im[Y(1040):Y(1050), X(1470):X(1477)].reshape(-1, 3).mean(0)]
    row = im[Y(1046), X(437):X(660)].mean(-1)
    half = np.where(row <= (row[0] + row[-1]) / 2)[0]
    rec['away_wing_half_fade_source_x'] = round(float((X(437) + half[0] - ox) / sx), 1) if len(half) else None
    rec['plate_top_rgb'] = [round(v, 1) for v in im[Y(948):Y(951), X(850):X(1070)].reshape(-1, 3).mean(0)]
    rec['plate_bottom_rgb'] = [round(v, 1) for v in im[Y(978):Y(982), X(850):X(1070)].reshape(-1, 3).mean(0)]
    rec['capsule_rgb'] = [round(v, 1) for v in im[Y(1015):Y(1025), X(900):X(915)].reshape(-1, 3).mean(0)]
    rec['red_cell_rgb'] = [round(v, 1) for v in im[Y(1010):Y(1030), X(1060):X(1078)].reshape(-1, 3).mean(0)]
    rec['housing_rgb'] = [round(v, 1) for v in im[Y(1041):Y(1044), X(860):X(1060)].reshape(-1, 3).mean(0)]
    rec['housing_side_rgb'] = [round(v, 1) for v in im[Y(1005):Y(1035), X(840):X(848)].reshape(-1, 3).mean(0)]
    _s = im[Y(975):Y(1010), X(736):X(776)].reshape(-1, 3)
    rec['score_rgb_p90'] = [round(v, 1) for v in np.percentile(_s, 90, axis=0)]
    for nm, bx in (('away_score', (700, 960, 815, 1022)), ('home_score', (1105, 960, 1220, 1022))):
        sb = im[Y(bx[1]):Y(bx[3]), X(bx[0]):X(bx[2])].mean(-1)
        mk = sb > 175
        rr = np.where(mk.any(1))[0]; cc2 = np.where(mk.any(0))[0]
        if len(rr):
            rec[nm + '_ink_source_box'] = [round((X(bx[0]) + cc2.min() - ox) / sx, 1), round((Y(bx[1]) + rr.min() - oy) / sy, 1), round((X(bx[0]) + cc2.max() - ox) / sx, 1), round((Y(bx[1]) + rr.max() - oy) / sy, 1)]
    strip = im[Y(1005):Y(1035), X(839):X(1019)].mean(-1)
    rec['capsule_has_separator_ticks'] = bool((strip.min(0) < strip.max() - 25).any())
    for name, box in (('away_logo', (440, 943, 660, 1051)), ('home_logo', (1258, 943, 1478, 1051))):
        sub = im[Y(box[1]):Y(box[3]), X(box[0]):X(box[2])]
        lum = sub.mean(-1); sat = sub.max(-1) - sub.min(-1)
        mask = (lum > 150) | (sat > 70)
        rows = np.where(mask.any(1))[0]; cols = np.where(mask.any(0))[0]
        if len(rows):
            rec[name + '_ink_source_box'] = [round((X(box[0]) + cols.min() - ox) / sx, 1),
                                             round((Y(box[1]) + rows.min() - oy) / sy, 1),
                                             round((X(box[0]) + cols.max() - ox) / sx, 1),
                                             round((Y(box[1]) + rows.max() - oy) / sy, 1)]
            rec[name + '_ink_source_size'] = [round((cols.max() - cols.min() + 1) / sx, 1),
                                              round((rows.max() - rows.min() + 1) / sy, 1)]
    out['sprite'][aspect] = rec

print(json.dumps(out, indent=1, default=J))
