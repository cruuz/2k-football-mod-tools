#!/usr/bin/env python3
"""Legibility metrics on the rendered 640x480 previews, the retail 2K5 label and ESPN.

Read-only. Prints one JSON object.
  python3 measure_readability.py <preview_dir>
Expects <preview_dir>/b72_first10_43.png/.json and _169 from the studio preview command.

Metric: counter depth. A '0' is legible only when its enclosed counter stays darker
than its stroke. depth = (stroke_peak - counter_floor) / stroke_peak, on the ink
channel (distance from the plate colour). Below about 0.35 the glyph reads as a blob.
"""
import json, sys
from pathlib import Path
from PIL import Image
import numpy as np

prev = Path(sys.argv[1])
FRAME = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
DAY = Path('/home/noah/Desktop/2K5-8 Editors/beta71_evidence/day/ksnip_20260915-154929.png')
out = {}


def counter_metrics(patch, plate_rgb):
    """patch = RGB float array of one glyph; ink = distance from the plate colour."""
    ink = np.abs(patch - np.asarray(plate_rgb)).mean(-1)
    if ink.max() <= 0:
        return None
    n = ink / ink.max()
    h, w = n.shape
    inner = n[max(1, h//4):max(2, h - h//4), max(1, w//4):max(2, w - w//4)]
    return {'stroke_peak_ink': round(float(ink.max()), 1),
            'counter_floor_ink': round(float(inner.min() * ink.max()), 1),
            'counter_depth': round(float(1 - inner.min()), 3),
            'mean_ink': round(float(ink.mean()), 1)}


for aspect in ('43', '169'):
    png = prev / f'b72_first10_{aspect}.png'
    meta = json.loads((prev / f'b72_first10_{aspect}.json').read_text())
    im = np.asarray(Image.open(png).convert('RGB'), dtype=float)
    q = meta['quads']
    plate = q['plate']
    plate_rgb = im[int(plate[1]) + 2, int(plate[0]) + 3]           # plate pixel clear of ink
    rec = {'plate_rgb': [round(v, 1) for v in plate_rgb]}
    for name, label in (('down:6', 'final_zero'), ('down:1', 'st_ordinal'), ('down:3', 'ampersand'),
                        ('down:0', 'leading_one'), ('down:5', 'tens_one')):
        if name not in q:
            continue
        x0, y0, x1, y1 = q[name]
        patch = im[int(round(y0)):int(round(y1)), int(round(x0)):int(round(x1))]
        rec[label] = {'quad_hud_px': [round(x1 - x0, 2), round(y1 - y0, 2)],
                      'raster_px': list(patch.shape[1::-1])}
        m = counter_metrics(patch, plate_rgb)
        if m:
            rec[label].update(m)
    # whole label strip: ink contrast against the plate
    xs = [q[k][0] for k in q if k.startswith('down:')] + [q[k][2] for k in q if k.startswith('down:')]
    ys = [q[k][1] for k in q if k.startswith('down:')] + [q[k][3] for k in q if k.startswith('down:')]
    strip = im[int(min(ys)):int(max(ys)) + 1, int(min(xs)):int(max(xs)) + 1]
    lum = strip.mean(-1)
    rec['strip'] = {'box_hud': [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)],
                    'raster_rows': int(max(ys)) - int(min(ys)) + 1,
                    'peak_luminance': round(float(lum.max()), 1),
                    'plate_luminance': round(float(np.asarray(plate_rgb).mean()), 1),
                    'michelson_contrast': round(float((lum.max() - np.asarray(plate_rgb).mean()) /
                                                      (lum.max() + np.asarray(plate_rgb).mean())), 3),
                    'fraction_of_strip_above_half_peak': round(float((lum > lum.max() * .5).mean()), 3)}
    out[aspect] = rec

# ---- retail 2K5's own down label, from the same xemu window (1132x670 over 640x480)
if DAY.is_file():
    im = np.asarray(Image.open(DAY).convert('RGB'), dtype=float)
    crop = im[586:620, 495:630]
    lum = crop.mean(-1)
    ink = lum > 200
    rows = np.where(ink.any(1))[0]; cols = np.where(ink.any(0))[0]
    sx, sy = 1132 / 640, 670 / 480
    out['retail_2k5_label'] = {
        'source': str(DAY), 'window': [1132, 670], 'assumed_hud_scale': [round(sx, 3), round(sy, 3)],
        'ink_rows_px': int(rows.max() - rows.min() + 1), 'ink_cols_px': int(cols.max() - cols.min() + 1),
        'cap_height_hud_px': round(float(rows.max() - rows.min() + 1) / sy, 2),
        'string_width_hud_px': round(float(cols.max() - cols.min() + 1) / sx, 2),
        'plate_luminance': round(float(np.median(lum[lum < 120])), 1),
        'peak_luminance': round(float(lum.max()), 1)}

# ---- what ESPN's own label becomes at the HUD footprint (area filter, the ideal)
if FRAME.is_file():
    frame = Image.open(FRAME).convert('RGB')
    box = (898, 955, 1021, 978)
    crop = frame.crop(box)
    for aspect, xs in (('43', 0.4444444444444444), ('169', 0.3333333333333333)):
        w = max(1, int(round(crop.width * xs))); h = max(1, int(round(crop.height * 448 / 1080)))
        small = np.asarray(crop.resize((w, h), Image.Resampling.BOX), dtype=float)
        lum = small.mean(-1)
        plate_rgb = np.asarray(frame.crop((898, 949, 1021, 953))).reshape(-1, 3).mean(0)
        out.setdefault('espn_at_hud_footprint', {})[aspect] = {
            'raster_px': [w, h], 'peak_luminance': round(float(lum.max()), 1),
            'plate_luminance': round(float(plate_rgb.mean()), 1),
            'michelson_contrast': round(float((lum.max() - plate_rgb.mean()) / (lum.max() + plate_rgb.mean())), 3),
            'fraction_above_half_peak': round(float((lum > lum.max() * .5).mean()), 3)}

# ---- does the ESPN label carry a dark outline? measure the ring just outside the ink
if FRAME.is_file():
    a = np.asarray(Image.open(FRAME).convert('RGB'), dtype=float)
    crop = a[949:984, 892:1027]
    lum = crop.mean(-1)
    ink = lum > 170
    from scipy import ndimage  # optional
    out['espn_outline'] = {'note': 'scipy present'} if True else {}
    grow = np.zeros_like(ink)
    for dy in (-2, -1, 0, 1, 2):
        for dx in (-2, -1, 0, 1, 2):
            grow |= np.roll(np.roll(ink, dy, 0), dx, 1)
    ring = grow & ~ink
    plate = lum[~grow]
    out['espn_outline'] = {
        'ink_mean_luminance': round(float(lum[ink].mean()), 1),
        'ring_2px_mean_luminance': round(float(lum[ring].mean()), 1),
        'plate_mean_luminance': round(float(plate.mean()), 1),
        'ring_is_darker_than_plate_by': round(float(plate.mean() - lum[ring].mean()), 1),
        'verdict': 'dark outline/shadow present' if lum[ring].mean() < plate.mean() - 3 else 'no outline'}

print(json.dumps(out, indent=1))
