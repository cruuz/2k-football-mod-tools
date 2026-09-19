#!/usr/bin/env python3
"""Measure the sprite scorebug's glyph cells against the ESPN reference frame.

Read-only. Prints one JSON object. Run from the repo worktree root:
  python3 "beta72_evidence/scorebug/measure_glyphs.py" > glyph_measurements.json

Everything is in three coordinate spaces:
  source   1920x1080 broadcast pixels, the layout's authoring space
  hud      the game's 640x448 HUD render target (what the Xbox rasterises)
  display  the modelled picture (1440x1080 at 4:3, 1920x1080 at 16:9)
"""
import json, math, sys
from pathlib import Path
from PIL import Image
import numpy as np

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/home/noah/2k-worktrees/opus-b72-scorebug')
FRAME = Path('/home/noah/Desktop/Broncos-vs-Chiefs-Week1-Highlights/frames/frame_012001.jpg')
SPRITE = REPO / 'data/nfl2k5_scorebug_sprite'

WIDE_CONTRACTION = 27 / 32
Y_SCALE = 448 / 1080                      # nfl2k5_scorebug_sprite.hud_box
X_SCALE = {'4:3': 640 / 1440, '16:9': 640 / 1920 / WIDE_CONTRACTION}
# what the game's widescreen patch then does to the authored HUD box
RASTER_X = {'4:3': X_SCALE['4:3'], '16:9': X_SCALE['16:9'] * WIDE_CONTRACTION}
DISPLAY_W = {'4:3': 1440, '16:9': 1920}

spec = json.loads((SPRITE / 'layout.json').read_text())
sheet = Image.open(SPRITE / 'template.png').convert('RGBA')


def alpha_of(cell):
    box = spec['cells'][cell]['box']
    return np.asarray(sheet.crop(box).getchannel('A'), dtype=float) / 255.0


def stem_runs(mask):
    """Horizontal run lengths of ink, per row, for a boolean mask."""
    runs = []
    for row in mask:
        n = 0
        for v in row:
            if v:
                n += 1
            elif n:
                runs.append(n); n = 0
        if n:
            runs.append(n)
    return runs


def bilinear_minify(a, out_w, out_h):
    """The sampler tools/nfl2k5_scorebug_projection.py:834-843 models (= NV2A, no mip)."""
    h, w = a.shape
    out = np.zeros((out_h, out_w))
    for y in range(out_h):
        ty = (y + .5) / out_h * h - .5
        iy = math.floor(ty); fy = ty - iy
        for x in range(out_w):
            tx = (x + .5) / out_w * w - .5
            ix = math.floor(tx); fx = tx - ix
            s = 0.
            for dx, dy, wgt in ((0,0,(1-fx)*(1-fy)), (1,0,fx*(1-fy)), (0,1,(1-fx)*fy), (1,1,fx*fy)):
                s += a[min(h-1, max(0, iy+dy)), min(w-1, max(0, ix+dx))] * wgt
            out[y, x] = s
    return out


def area_minify(a, out_w, out_h):
    im = Image.fromarray((a * 255).round().astype('uint8'), 'L')
    return np.asarray(im.resize((out_w, out_h), Image.Resampling.BOX), dtype=float) / 255.0


def sampled_fraction(n_texels, n_pixels):
    """Fraction of texel centres that at least one bilinear tap touches."""
    touched = set()
    for p in range(int(round(n_pixels))):
        t = (p + .5) / n_pixels * n_texels - .5
        touched.add(min(n_texels - 1, max(0, math.floor(t))))
        touched.add(min(n_texels - 1, max(0, math.floor(t) + 1)))
    return len(touched) / n_texels


report = {'coordinate_spaces': {'y_scale_hud_per_source': Y_SCALE,
                                'x_scale_hud_per_source': X_SCALE,
                                'x_raster_hud_per_source_after_widescreen_patch': RASTER_X}}

# ---------------------------------------------------------------- glyph sets
sets = {}
for name, gs in spec['glyph_sets'].items():
    if name == 'ticks':
        continue
    cap = gs['cap_height']
    field = next((f for f in spec['fields'] if f['glyph_set'] == name), None)
    sample = {'score': '0', 'clock': '0', 'small': '0', 'label': '0'}[name]
    a = alpha_of(gs['glyphs'][sample]['cell'])
    ink = a > .5
    runs = stem_runs(ink)
    stem_texels = float(np.median(runs)) if runs else 0.
    cw, ch = gs['glyphs'][sample]['size']
    entry = {'cell_texels': [cw, ch], 'cap_height_source_px': cap,
             'stem_width_texels_median': round(stem_texels, 2),
             'field': field['name'] if field else None,
             'colour': field['colour'] if field else None}
    for aspect in ('4:3', '16:9'):
        gw = cw * RASTER_X[aspect]
        gh = ch * Y_SCALE
        bil = bilinear_minify(a, max(1, int(round(gw))), max(1, int(round(gh))))
        area = area_minify(a, max(1, int(round(gw))), max(1, int(round(gh))))
        entry[aspect] = {
            'glyph_hud_px': [round(gw, 2), round(gh, 2)],
            'cap_height_hud_px': round(cap * Y_SCALE, 2),
            'cap_height_display_px': round(cap * Y_SCALE * 1080 / 448, 2),
            'minification_x': round(cw / gw, 2), 'minification_y': round(ch / gh, 2),
            'stem_width_hud_px': round(stem_texels * RASTER_X[aspect], 2),
            'texel_columns_sampled': round(sampled_fraction(cw, gw), 3),
            'texel_rows_sampled': round(sampled_fraction(ch, gh), 3),
            'bilinear_vs_area_mean_abs_alpha_error': round(float(np.abs(bil - area).mean()), 4),
            'bilinear_vs_area_max_abs_alpha_error': round(float(np.abs(bil - area).max()), 4),
            'bilinear_peak_alpha': round(float(bil.max()), 3),
            'area_peak_alpha': round(float(area.max()), 3),
        }
    sets[name] = entry
report['glyph_sets'] = sets

# --------------------------------------------------------- string measurement
def string_width(setname, tokens):
    gs = spec['glyph_sets'][setname]['glyphs']
    total = sum(gs[t]['advance'] for t in tokens)
    return total - (gs[tokens[-1]]['advance'] - gs[tokens[-1]]['size'][0])

down = next(f for f in spec['fields'] if f['name'] == 'down')
tokens = ['1', 'st', ' ', '&', ' ', '1', '0']
w_src = string_width('label', tokens)
report['down_label_1st_and_10'] = {
    'tokens': tokens, 'glyph_quads_used': len([t for t in tokens if t != ' ']),
    'quad_capacity': down['slots'],
    'string_width_source_px': w_src,
    'field_width_limit_source_px': down['box'][2] - down['box'][0],
    'compressed': w_src > (down['box'][2] - down['box'][0]),
    'espn_reference_ink_source_px': [spec['reference_boxes']['down'][2] - spec['reference_boxes']['down'][0],
                                     spec['reference_boxes']['down'][3] - spec['reference_boxes']['down'][1]],
}
for aspect in ('4:3', '16:9'):
    report['down_label_1st_and_10'][aspect] = {
        'string_width_hud_px': round(w_src * RASTER_X[aspect], 2),
        'string_width_display_px': round(w_src * RASTER_X[aspect] * DISPLAY_W[aspect] / 640, 2),
        'cap_height_hud_px': round(23 * Y_SCALE, 2),
    }

# ----------------------------------------------------------- ESPN reference
if FRAME.is_file():
    frame = np.asarray(Image.open(FRAME).convert('RGB'), dtype=float)
    box = spec['reference_boxes']['down']                       # 898,955,1021,978
    crop = frame[box[1]-6:box[3]+6, box[0]-6:box[2]+6]
    lum = crop.mean(-1)
    ink = lum > 170                                             # white label ink
    runs = stem_runs(ink)
    rows = np.where(ink.any(1))[0]
    cols = np.where(ink.any(0))[0]
    # background (plate) and shadow around the ink
    plate = frame[box[1]-4:box[1]-1, box[0]:box[2]].reshape(-1, 3).mean(0)
    white = crop[ink].mean(0) if ink.any() else np.zeros(3)
    dark = lum < 80
    espn = {'ink_box_source': box,
            'measured_ink_rows': [int(rows.min()), int(rows.max())] if len(rows) else None,
            'measured_cap_height_px': int(rows.max() - rows.min() + 1) if len(rows) else None,
            'measured_ink_width_px': int(cols.max() - cols.min() + 1) if len(cols) else None,
            'stem_width_px_median': float(np.median(runs)) if runs else None,
            'stem_width_px_p25_p75': [float(np.percentile(runs, 25)), float(np.percentile(runs, 75))] if runs else None,
            'plate_rgb_above_ink': [round(v, 1) for v in plate],
            'ink_rgb_mean': [round(v, 1) for v in white],
            'dark_shadow_pixel_fraction_in_crop': round(float(dark.mean()), 3),
            'ink_vs_plate_luminance_ratio': round(float(white.mean() / max(plate.mean(), 1)), 2)}
    # the same for the clock capsule digits and the quarter
    for key, thresh, label in (('clock', None, 'clock'), ('quarter', None, 'quarter'), ('play_clock', None, 'play_clock')):
        b = spec['reference_boxes'][key]
        sub = frame[b[1]:b[3], b[0]:b[2]].mean(-1)
        d = sub < 110 if key in ('clock', 'quarter') else sub > 150
        r = np.where(d.any(1))[0]; c = np.where(d.any(0))[0]
        rr = stem_runs(d)
        espn[label] = {'box': b,
                       'cap_height_px': int(r.max() - r.min() + 1) if len(r) else None,
                       'ink_width_px': int(c.max() - c.min() + 1) if len(c) else None,
                       'stem_width_px_median': float(np.median(rr)) if rr else None}
    report['espn_reference_frame_012001'] = espn

# ------------------------------------------------- P8 palette pressure
try:
    sys.path.insert(0, str(REPO))
    sys.path.insert(0, str(REPO / 'tools'))
    from mod_editor.core import nfl2k5_scorebug_sprite as sprite
    c43 = sprite.compile_folder(SPRITE, False)
    from mod_editor.core.nfl2k5_scorebug_assets import quantize_alpha_aware
    palette, indices = quantize_alpha_aware(c43.atlas.convert('RGBA'), 256)
    idx = np.asarray(indices, dtype=np.uint8).reshape(c43.atlas.height, c43.atlas.width) \
        if not isinstance(indices, (bytes, bytearray)) else \
        np.frombuffer(indices, dtype=np.uint8).reshape(c43.atlas.height, c43.atlas.width)
    pal = {'palette_entries_used': len(palette), 'palette_capacity': 256}
    for group, names in (('label', [g['cell'] for g in spec['glyph_sets']['label']['glyphs'].values()]),
                         ('small', [g['cell'] for g in spec['glyph_sets']['small']['glyphs'].values()]),
                         ('clock', [g['cell'] for g in spec['glyph_sets']['clock']['glyphs'].values()]),
                         ('score', [g['cell'] for g in spec['glyph_sets']['score']['glyphs'].values()]),
                         ('body/plate/wing', ['body', 'plate', 'wing', 'housing', 'capsule', 'red', 'flag'])):
        used = set()
        for n in set(names):
            if n not in c43.cells:
                continue
            x0, y0, x1, y1 = c43.cells[n]
            used.update(np.unique(idx[y0:y1, x0:x1]).tolist())
        pal[group + '_palette_entries'] = len(used)
        if group in ('label', 'small'):
            alphas = sorted({palette[i][3] if len(palette[i]) > 3 else 255 for i in used})
            pal[group + '_distinct_alpha_levels'] = len(alphas)
            pal[group + '_alpha_levels'] = alphas
    report['atlas_p8_palette'] = pal
    report['atlas'] = {'size': list(c43.atlas.size), 'mip_levels': 1,
                       'note': 'mod_editor/core/nfl2k5_scorebug_assets.py:350 packs one level only'}
except Exception as exc:                                            # pragma: no cover
    report['atlas_p8_palette'] = {'error': repr(exc)}

print(json.dumps(report, indent=1))
