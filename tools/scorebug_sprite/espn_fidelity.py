"""b778 sb3/sb4: the scorebar's team gradient, rim light, and sb4's connected clock pill and attached plate tab.

Noah (10/23 ~00:45): "The border and glow of the real score bug is still better than the one we're using in-game,
as well as the gradient color being deeper and more over the logo. It's just not accurate enough." and "it doesn't
even have a gradient on the down and distance". The measurements come from the 2026 ESPN bars at 1920x1080
(reports/b72_s9/broadcast_away_median.png and broadcast_home_median.png, and the read-only stills in
.b77-scratch/b778/sb2/ref_bars.png). No broadcast pixel is copied: each cell is rebuilt from the measured profile.

sb4 (Noah 10/23 ~02:00): "The play clock font is too large, and there's like a black closing section around the
12:32 and third quarter. It looks like one, and then the 45-second play clock is added on. It's not connected like
it is on the ESPN bar. Also, I'm not seeing enough of a gradient on the down and distance, and unlike the ESPN, the
down and distance now just looks like a square. It's not blending into the top of it." Measured on the read-only
2026 Broncos at Chiefs still: one 243x40 pill from x 839 to 1082 with 2 px dividers at x 902.5 and 1021.5, quarter
ink 32x18, clock ink 26 tall, play clock ink 15x19; the plate is a 270 px wide tab whose top is the bar's top edge
and whose sides taper to 237 px at the bottom, with a bright crest, deep body, dark lower edge and a soft drop
shadow over the bar.

Changes, all inside the existing quad budget:

wing     The s12 coverage field keeps its fit near the outer rail but the top and bottom glow are re-measured
         (a2 .45 -> 1.05, d2 13.82 -> 14, d3 461.6 -> 350; a3 1.5 -> 2.0, d4 2.839 -> 3.2, d5 83.55 -> 95). A
         window clears the glow before the score column, where the broadcast shows the body again; this keeps
         the white score/timeout/record glyphs on the dark body the way ESPN draws them. The result is more
         team colour over the mark and a darker falloff between the mark and the score.
plate    sb4 replaces the rounded 91x15 cell with a measured 240x48 trapezoid, authored down to the 90x19
         HUD footprint: the wide top edge sits on the bar's top rail, the sides taper into the body and the
         bottom carries a dark lower edge and drop shadow. The row profile keeps a bright crest, deepens the
         body and drives the lower edge dark, so the strong vertical gradient survives the possession tint. A
         second untinted white-coverage cell (plate_gloss) lays the still's desaturated top bevel over the tint.
tab      sb5 (Noah 10/23 ~03:40: "a weird shape ... not the actual shape on the ESPN one with its smooth curves, and
         it doesn't blend into the gradient of the team possessing the ball") replaces sb4's trapezoid. The tab
         hangs from the rail with S-curved shoulders fitted to the still's edge, vertical sides, rounded lower
         corners and a flat bottom; the multiplier lights the sides and darkens the centre under the label, with
         a glint row and bright band across the top. plate_gloss now carries the glint and the thin desaturated
         rim light. The runtime tints the tab with the midpoint of the possessing team's wing display shade and
         its sourced plate accent, so the tab continues that team's side of the bar (TAB_* below).
capsule  sb4 replaces the 183 px capsule with one 243x40 pill spanning quarter, game clock and play clock, with
         the still's 2 px gray dividers at x 902.5 and 1021.5. The play-clock red state is the pill's own right
         cap (white rim and outline included) so it cannot read as a second box. The quarter label shrinks to the
         measured 18 px superscript height (19 px field), the clock ink to 26 px (27 px field) and the play clock
         to 19 px. The score digits lose sb3's gray bevel and widen 6% to the still's stroke, since the bevel read
         as a dirty outline at the HUD footprint. Static cells are authored at the 16:9 footprint.
rim      The two rim cells are re-authored as bright coverage: the 2026 bars keep a team-coloured light on the
         outer rail and lower lip. The runtime lightens each rim tint from the wing's own shade (the pre-accent
         default) and the white coverage lays it over the wing and body. No new quad is added.
buf      The standing buffalo is Buffalo's alternate. The shipped mark is replaced with the charging primary
         buffalo from the already-shipped official 128 px set, resampled to the 64 px cell.

python3 tools/scorebug_sprite/espn_fidelity.py [--folder FOLDER] [--check]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(ROOT/'tools/scorebug_sprite')]
DEFAULT_FOLDER = ROOT / 'data/nfl2k5_scorebug_sprite'
LOGOS = ROOT / 'data/nfl2k5_scorebug_mnf' / 'logos'
ASSET_LOGOS = ROOT / 'data/nfl2k5_scorebug_assets' / 'logos'
RECORD = 'b778_sb3_espn_fidelity'
CAPSULE_RECORD = 'b778_sb4_connected_clock'
PLATE_RECORD = 'b778_sb4_plate_tab'

WING = dict(a1=0.8761, d1=41.19, v1=0.2879, a2=1.05, d2=14.0, d3=350.0,
            a3=2.0, d4=3.2, d5=95.0, window_start=250.0, window_end=330.0)
# sb4: the plate quad is the still's 270x48 footprint (top on the bar's rail and
# the last four rows the drop shadow over the bar). Rows 0..42 are the tab, the
# last five the shadow. 255 is the full possession tint.
PLATE_LAYOUT = [828, 944, 1098, 990]
PLATE_SOURCE = (240, 48)
PLATE_TAB_ROWS = 42
PLATE_ROWS = [1.00, 1.00, 0.99, 0.96, 0.90, 0.81, 0.76, 0.80, 0.83, 0.85, 0.86,
              0.86, 0.86, 0.87, 0.87, 0.87, 0.87, 0.87, 0.87, 0.87, 0.87, 0.87,
              0.87, 0.87, 0.86, 0.86, 0.86, 0.86, 0.86, 0.85, 0.85, 0.85, 0.84,
              0.83, 0.81, 0.78, 0.73, 0.66, 0.57, 0.46, 0.33, 0.20]
PLATE_SHADOW_ROWS = [0.62, 0.48, 0.34, 0.21, 0.10, 0.03]
# sb5 (Noah 10/23 ~03:40): "the down and distance above it looks bad. It's like a weird shape. It's not the
# actual shape on the ESPN one with its smooth curves, and it doesn't blend into the gradient of the team
# possessing the ball." Measured on the read-only Broncos at Chiefs still (sb3/ds/work/ref_full.png) and the
# b72 broadcast away median. The tab hangs from the bar's top rail: an S-curved shoulder flares out of the rail
# on each side (box-local layout px; a cubic fitted to the still's 50% edge rows 2..19, RMS 0.1 px), the sides
# are vertical 246 px apart, the lower corners are 7 px arcs and the flat bottom sits at 39.5 px (bar y 983.5).
# Colour: the lit sides are the brightest part (the peak ~13 px in from each edge) and the centre under the
# label falls to 0.56 of it; across the top a glint row, a darker row and a bright band run the full width;
# a thin desaturated rim light outlines the shoulders, sides and bottom. The sb4 records below stay frozen.
TAB_DESIGN = (270, 46)
TAB_SUPERSAMPLE = 8
TAB_FLARE = ((-1.5, 0.0), (0.5, 0.0), (11.8, 16.5), (11.8, 18.0))
TAB_SIDE = 11.8
TAB_CORNER = 7.0
TAB_BOTTOM = 39.5
TAB_PEAK = 0.80
TAB_ACROSS = ((0, 0.76), (1, 0.78), (4, 0.88), (7, 0.95), (10, 0.99), (13, 1.0), (16, 0.99), (19, 0.95),
              (22, 0.90), (25, 0.87), (28, 0.85), (31, 0.81), (34, 0.78), (37, 0.75), (40, 0.735), (43, 0.70),
              (46, 0.68), (49, 0.655), (52, 0.64), (55, 0.62), (58, 0.60), (61, 0.58), (64, 0.565), (70, 0.555))
TAB_DOWN = ((0, 0.70), (1.5, 0.70), (2.5, 0.58), (3.5, 0.62), (4.5, 0.95), (5.5, 1.04), (6.5, 0.98), (8, 0.97),
            (10, 1.0), (28, 1.03), (31, 1.0), (33, 0.95), (35, 0.91), (37, 0.90), (38.5, 0.95), (39.5, 0.90))
TAB_BAND = ((0, 0.56), (1.5, 0.54), (2.5, 0.42), (3.5, 0.44), (4.5, 0.70), (5.5, 0.86), (6.5, 0.76), (7.5, 0.60),
            (8.5, 0.0), (36.5, 0.0), (38.0, 0.62), (39.5, 0.60))
TAB_GLINT = ((0, 0.40), (1.5, 0.42), (2.5, 0.06), (4.5, 0.0), (5.5, 0.12), (6.5, 0.08), (7.5, 0.0))
TAB_RIM = 0.40
TAB_HALO = 0.55
TAB_HALO_WHITE = 0.24
TAB_HALO_SHADE = 0.62
TAB_EDGE_SOFT = 1.1
TAB_RECORD = 'b778_sb5_tab_shape'
# sb3's frozen provenance, kept so re-running this author does not rewrite history.
SB3_PLATE_ROWS = [0.34, 0.42, 0.62, 0.84, 0.82, 0.79, 0.77, 0.75, 0.74, 0.73, 0.72,
                  0.71, 0.71, 0.70, 0.70, 0.70, 0.70, 0.70, 0.69, 0.69, 0.69, 0.69,
                  0.68, 0.68, 0.68, 0.68, 0.67, 0.67, 0.67, 0.66, 0.66, 0.65, 0.63,
                  0.60, 0.55, 0.47, 0.36, 0.24]
# sb4: one pill from the quarter to the play clock. The still's dividers sit at
# layout x 902.5 and 1021.5; the red state is the pill's own right cap.
CAPSULE_LAYOUT = [839, 999, 1082, 1039]
CAPSULE_SOURCE = (240, 40)
CAPSULE_DIVIDERS = (63.2, 180.2)
CAPSULE_ROWS = ([0.57, 0.98, 1.00, 0.945, 0.99] + [0.968] * 32 + [0.965, 0.995, 0.86])
RED_LAYOUT = [1023, 999, 1082, 1039]
# sb3's drawn widths, kept while the height drops to the measured 18 px so the
# superscript label keeps its broadcast width. Re-applied every run, so the
# author stays idempotent.
QUARTER_METRICS = {
    '1ST': (31.5, 33.5), '1st': (31.5, 33.5),
    '2ND': (43.5, 45.5), '2nd': (43.5, 45.5),
    '3RD': (42.5, 44.5), '3rd': (42.5, 44.5),
    '4TH': (42.5, 44.5), '4th': (42.5, 44.5),
    'OT': (37.278, 39.278),
    **{f'OT{i}': (37.278, 39.278) for i in range(10)},
}
# sb3's clock metrics, widened by the still's 99 px ink at the 26 px height.
CLOCK_WIDTH_SCALE = 1.0710
SCORE_WIDTH_SCALE = 1.060
SCORE_METRICS = {
    '0': (48.105, 52.105), '1': (24.543, 28.543), '2': (45.16, 49.16),
    '3': (46.142, 50.142), '4': (50.069, 54.069), '5': (48.105, 52.105),
    '6': (48.105, 52.105), '7': (38.288, 42.288), '8': (48.105, 52.105),
    '9': (48.105, 52.105), ' ': (0.0, 6.0),
}
CLOCK_METRICS = {
    '0': (21.808, 23.808), '1': (12.96, 14.96), '2': (21.808, 23.808),
    '3': (21.808, 23.808), '4': (21.808, 23.808), '5': (21.808, 23.808),
    '6': (21.808, 23.808), '7': (20.52, 22.52), '8': (21.808, 23.808),
    '9': (21.808, 23.808), ':': (7.0, 9.0), ' ': (0.0, 6.0),
}
RIM_SOURCE = (523, 110)
WING_SOURCE = (340, 110)


def _box(spec, name):
    return spec['cells'][name]['box']


def _filter(image, size):
    return image.resize(size, Image.Resampling.BOX)


def _white(size, alpha):
    image = Image.new('RGBA', size, (255, 255, 255, 255))
    image.putalpha(Image.fromarray(np.rint(np.clip(alpha, 0, 1) * 255).astype('uint8'), 'L'))
    return image


def rounded_mask(size, radius, supersample=4):
    width, height = size
    image = Image.new('L', (width * supersample, height * supersample), 0)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, width * supersample - 1, height * supersample - 1),
                           radius * supersample, fill=255)
    return np.asarray(image.resize((width, height), Image.Resampling.BOX), dtype=float) / 255


def wing_alpha(size=WING_SOURCE, params=WING):
    width, height = size
    y, x = np.mgrid[0:height, 0:width].astype(float)
    edge = params['a1'] * np.exp(-x / params['d1']) * (1 - params['v1'] * y / max(1, height - 1))
    window = np.clip((params['window_end'] - x) / (params['window_end'] - params['window_start']), 0, 1)
    top = params['a2'] * np.exp(-y / params['d2']) * np.exp(-x / params['d3']) * window
    bottom = params['a3'] * np.exp(-(height - 1 - y) / params['d4']) * np.exp(-x / params['d5'])
    cover = np.clip(edge + top + bottom, 0, 1)
    shape = rounded_mask((width, height), 8)
    return cover * shape, cover


def wing_cell(size):
    cover, _ = wing_alpha()
    image = _filter(_white(WING_SOURCE, cover), size)
    arr = np.asarray(image).copy()
    arr[:, -1, 3] = 0
    arr[..., 3] = np.minimum.accumulate(arr[..., 3], axis=1)
    return Image.fromarray(arr, 'RGBA'), cover


def _profile(values, height):
    return np.interp(np.arange(height), np.arange(len(values)), values)


def _bezier(points, steps=4001):
    t = np.linspace(0.0, 1.0, steps)[:, None]
    p0, p1, p2, p3 = (np.asarray(point, float) for point in points)
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3


def tab_left_edge(y):
    """Left edge of the sb5 tab in box-local layout px at row(s) y; nan where the tab has ended.

    The shoulder is the measured S curve out of the rail (TAB_FLARE), the side is vertical, and the
    lower corner is a TAB_CORNER radius arc into the flat bottom. The right edge is the mirror image."""
    y = np.asarray(y, float)
    curve = _bezier(TAB_FLARE)
    flare_end = TAB_FLARE[-1][1]
    x = np.where(y < flare_end, np.interp(y, curve[:, 1], curve[:, 0]), TAB_SIDE)
    cy = TAB_BOTTOM - TAB_CORNER
    dy = np.clip(y - cy, 0, None)
    arc = TAB_SIDE + TAB_CORNER - np.sqrt(np.clip(TAB_CORNER ** 2 - dy ** 2, 0, None))
    x = np.where(y > cy, arc, x)
    return np.where(y <= TAB_BOTTOM, x, np.nan)


def _tab_fields(supersample=TAB_SUPERSAMPLE):
    """Supersampled tab coverage, tint multiplier, halo and rim-light coverage in layout space."""
    from PIL import ImageFilter
    width, height = TAB_DESIGN
    xs = (np.arange(width * supersample) + 0.5) / supersample
    ys = (np.arange(height * supersample) + 0.5) / supersample
    left = tab_left_edge(ys)[:, None]
    right = width - left
    x = xs[None, :]
    with np.errstate(invalid='ignore'):
        inside = (x >= left) & (x <= right)
        across = np.where(inside, np.minimum(x - left, right - x), 0.0)
    inside = inside & ~np.isnan(left)
    mask = inside.astype(float)
    # The shoulder tips meet the rail at the quad's own edge; fade them over 2.5 px so the
    # quad boundary never shows as a vertical cut through the rail.
    mask *= np.clip(np.minimum(x, width - x) / 2.5, 0, 1)
    shade = np.interp(across, *zip(*TAB_ACROSS)) * np.interp(ys, *zip(*TAB_DOWN))[:, None]
    band = np.interp(ys, *zip(*TAB_BAND))[:, None]
    value = TAB_PEAK * np.maximum(shade, band)

    def blur(field, radius):
        image = Image.fromarray(np.rint(np.clip(field, 0, 1) * 255).astype('uint8'), 'L')
        return np.asarray(image.filter(ImageFilter.GaussianBlur(radius * supersample)), float) / 255

    solid = inside.astype(float)
    # Pad above the box with the first row, so the blur does not invent an edge along the rail.
    pad = 4 * supersample
    padded = np.vstack([np.repeat(solid[:1], pad, axis=0), solid])
    soft = blur(padded, TAB_EDGE_SOFT)[pad:]
    halo = TAB_HALO * np.clip(soft * 2.0, 0, 1) * (1 - solid)
    halo[ys < TAB_FLARE[-1][1] * 0.5] = 0
    rim = TAB_RIM * np.clip((1 - soft) * 2.2, 0, 1) * solid
    # The still's outline is a light, desaturated line straddling the edge: white coverage over the halo too.
    rim = np.maximum(rim, TAB_HALO_WHITE / TAB_HALO * halo)
    return mask, value, halo, rim, ys


def plate_cell(size):
    """sb5: the possession tab, a neutral multiplier the runtime tints with the possessing team's shade.

    Coverage and colour are built in layout space at TAB_SUPERSAMPLE x, then area-filtered with
    premultiplied alpha down to the HUD footprint so the curves stay anti-aliased."""
    mask, value, halo, _rim, _ys = _tab_fields()
    alpha = np.clip(mask + halo, 0, 1)
    colour = np.where(mask > 0, value, TAB_PEAK * TAB_HALO_SHADE)
    premultiplied = colour * alpha

    def down(field):
        return np.asarray(Image.fromarray(field.astype('float32'), 'F').resize(size, Image.Resampling.BOX), float)

    a = down(alpha)
    c = down(premultiplied)
    plain = down(colour)
    rgb = np.where(a > 1e-4, c / np.maximum(a, 1e-4), plain)
    rgb = np.rint(np.clip(rgb, 0, 1) * 255)
    pixels = np.dstack([rgb, rgb, rgb, np.rint(np.clip(a, 0, 1) * 255)]).astype('uint8')
    return Image.fromarray(pixels, 'RGBA')


def _capsule_rgb(width, height, dividers=()):
    rgb = np.repeat((_profile(CAPSULE_ROWS, height) * 255)[:, None], width, axis=1)
    for divider in dividers:
        left = int(round(divider)) - 1
        rgb[3:height - 3, left:left + 2] = 160
    return np.repeat(rgb[..., None], 3, axis=2)


def capsule_cell(size):
    width, height = CAPSULE_SOURCE
    mask = rounded_mask((width, height), height // 2)
    rgb = _capsule_rgb(width, height, CAPSULE_DIVIDERS)
    ring = np.clip(mask - rounded_mask((width, height), height // 2 - 1), 0, 1)
    rgb = np.where(ring[..., None] > .35, 195, rgb)
    arr = np.dstack([rgb, mask * 255]).astype('uint8')
    return _filter(Image.fromarray(arr, 'RGBA'), size)


def gloss_cell(size):
    """sb5: untinted white light on the tab: the rail glint across its top rows, a faint crest on the
    top band and the thin rim light that runs down the shoulders, sides and bottom (desaturated, so
    it cannot come from the team tint)."""
    mask, _value, _halo, rim, ys = _tab_fields()
    top = np.interp(ys, *zip(*TAB_GLINT))[:, None] * mask
    alpha = np.clip(np.maximum(top, rim), 0, 1)
    a = np.asarray(Image.fromarray(alpha.astype('float32'), 'F').resize(size, Image.Resampling.BOX), float)
    pixels = np.dstack([np.full(a.shape + (3,), 255.0), np.rint(np.clip(a, 0, 1) * 255)]).astype('uint8')
    return Image.fromarray(pixels, 'RGBA')


def rim_cell(size, side):
    """White coverage cell for the bright rail the runtime tint supplies.

    The 2026 bars keep a bright team-coloured light on the outer rail and the lower lip; a white coverage
    cell under a lifted team tint reproduces it without inventing white paint. The top light is strong at the
    outer corners and fades before the centre; the lower lip is strongest at the centre. The outer one or two
    source pixels stay faint, so the wing's own colour is still the outermost edge.
    """
    width, height = RIM_SOURCE
    outer = np.arange(width, dtype=float)
    if side == 'home':
        outer = width - 1 - outer
    inner = width - 1 - outer
    centre = np.exp(-inner / 170.0)
    y = np.arange(height, dtype=float)[:, None]

    amplitude = 0.80 if side == 'away' else 0.55
    side = amplitude * np.exp(-outer[None, :] / 3.0)
    side = side * (0.84 + 0.16 * np.exp(-((y - 6.0) / 10.0) ** 2))
    top = 0.34 * np.exp(-y / 2.8) * np.exp(-outer[None, :] / 130.0)
    bottom = 0.30 * np.exp(-(height - 1 - y) / 2.4) * (0.35 + 0.65 * centre[None, :])
    alpha = np.clip(np.maximum(side, np.maximum(top, bottom)), 0, 1)
    pixels = np.dstack([np.full((height, width, 3), 255.0), alpha * 255]).astype('uint8')
    return _filter(Image.fromarray(pixels, 'RGBA'), size)


def buf_mark():
    source = Image.open(ASSET_LOGOS / 'buf.png').convert('RGBA')
    bounds = source.getchannel('A').getbbox()
    if bounds is None:
        raise ValueError('The official Buffalo mark is empty')
    source = source.crop(bounds)
    scale = 62 / max(source.width, source.height)
    mark = source.resize((max(1, round(source.width * scale)), max(1, round(source.height * scale))),
                         Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    canvas.alpha_composite(mark, ((64 - mark.width) // 2, (64 - mark.height) // 2))
    return canvas


def measurements(spec, sheet):
    cells = spec['cells']
    wing = np.asarray(sheet.crop(tuple(cells['wing']['box'])))[..., 3]
    plate = np.asarray(sheet.crop(tuple(cells['plate']['box'])))[..., :3]
    capsule = np.asarray(sheet.crop(tuple(cells['capsule']['box'])))[..., :3]
    away_rim = np.asarray(sheet.crop(tuple(cells['away_rim']['box'])))
    return dict(
        wing_outer=float(wing[len(wing) // 2, 0]),
        wing_logo_top=float(wing[int(len(wing) * .06), int(len(wing[0]) * .06)]),
        wing_inner=float(wing[len(wing) // 2, -1]),
        plate_top=[int(v) for v in plate[1, len(plate[0]) // 2]],
        plate_body=[int(v) for v in plate[len(plate) // 2, len(plate[0]) // 2]],
        plate_bottom=[int(v) for v in plate[-2, len(plate[0]) // 2]],
        capsule_top=int(capsule[0, len(capsule[0]) // 2].mean()),
        capsule_middle=int(capsule[len(capsule) // 2, len(capsule[0]) // 2].mean()),
        capsule_bottom=int(capsule[-1, len(capsule[0]) // 2].mean()),
        rim_side=float(away_rim[len(away_rim) // 2, 0, 3]),
        rim_side_rgb=[int(v) for v in away_rim[len(away_rim) // 2, 0, :3]],
        rim_top_rgb=[int(v) for v in away_rim[1, len(away_rim[0]) // 8, :3]],
        rim_centre=float(away_rim[len(away_rim) // 2, len(away_rim[0]) // 2, 3]),
    )


def apply(folder=DEFAULT_FOLDER, check=False):
    spec = json.loads((folder / 'layout.json').read_text(encoding='utf-8'))
    with Image.open(folder / 'template.png') as image:
        sheet = image.convert('RGBA')
    logos_before = (LOGOS / 'buf.png').read_bytes()
    buf = buf_mark()

    # sb4 cells live in the empty lower-left of the template so the old sb3
    # capsule and housing pixels cannot be picked up by the packer.
    # Authored at the 16:9 HUD footprint (the smallest aspect), as the SD
    # sampling rule requires; the authoring functions oversample then box-filter.
    spec['cells']['capsule'] = {'box': [1200, 360, 1281, 376]}
    spec['cells']['plate'] = {'box': [1200, 404, 1290, 423]}
    spec['cells']['red'] = {'box': [1200, 430, 1219, 446]}
    spec['cells']['plate_gloss'] = {'box': [1200, 450, 1290, 469]}
    sizes = {name: (_box(spec, name)[2] - _box(spec, name)[0], _box(spec, name)[3] - _box(spec, name)[1])
             for name in ('wing', 'home_wing', 'plate', 'plate_gloss', 'capsule', 'red', 'away_rim', 'home_rim')}
    spec['cells'].pop('highlight', None)
    spec['cells'].pop('housing', None)
    spec['static'][:] = [row for row in spec['static'] if row['name'] not in ('highlight', 'housing')]
    for name, expected in (('wing', (113, 45)), ('home_wing', (113, 45)), ('plate', (90, 19)),
                           ('plate_gloss', (90, 19)), ('capsule', (81, 16)), ('red', (19, 16)),
                           ('away_rim', (174, 45)), ('home_rim', (174, 45))):
        if sizes[name] != expected:
            raise SystemExit('The %s cell changed size; refusing to re-author (%s)' % (name, sizes[name]))
    statics = {row['name']: row for row in spec['static']}
    statics['capsule']['box'] = list(CAPSULE_LAYOUT)
    statics['red']['box'] = list(RED_LAYOUT)
    statics['plate']['box'] = list(PLATE_LAYOUT)
    if 'plate_gloss' not in statics:
        spec['static'].append({'name': 'plate_gloss', 'box': list(PLATE_LAYOUT), 'cell': 'plate_gloss',
                               'material': 3, 'tint': 'none', 'z': -16.8})
        statics = {row['name']: row for row in spec['static']}
    statics['plate_gloss']['box'] = list(PLATE_LAYOUT)
    # sb4: the still's quarter ink is 32x18, clock 26 tall, play clock 15x19.
    # The quarter's horizontal metrics are compensated so the label keeps the
    # measured width while its height shrinks to the superscript style.
    # The play clock formatter prints digits only; drop the legacy word tokens
    # that no field can reach so the atlas keeps only sampled cells.
    small = spec['glyph_sets']['small']['glyphs']
    for token in [token for token in small if not token.isdigit()]:
        del small[token]
    fields = {row['name']: row for row in spec['fields']}
    fields['quarter'].update(box=[846, 1010, 900, 1028], anchor=[871, 1010], size=19)
    fields['clock'].update(box=[906, 1006, 1014, 1034], anchor=[960, 1006], size=27)
    fields['play_clock'].update(box=[1023, 1010, 1076, 1029], anchor=[1051, 1010], size=19)
    fields['away_score'].update(box=[696, 965, 816, 1018], anchor=[756, 965], size=56)
    fields['home_score'].update(box=[1095, 965, 1215, 1018], anchor=[1155, 965], size=56)
    quarter = spec['glyph_sets']['quarter']
    scale = quarter['cap_height'] / 19
    for token, glyph in quarter['glyphs'].items():
        if token.startswith('OT'):
            # reports/b76_sbfix/author.py owns the overtime token metrics; its
            # committed-art check rebuilt them at 37.278 and must stay true.
            glyph['size'][0], glyph['advance'] = 37.278, 39.278
            continue
        width, advance = QUARTER_METRICS[token]
        glyph['size'][0] = width * scale
        glyph['advance'] = advance * scale
    clock = spec['glyph_sets']['clock']
    for token, glyph in clock['glyphs'].items():
        width, advance = CLOCK_METRICS[token]
        glyph['size'][0] = width * CLOCK_WIDTH_SCALE
        glyph['advance'] = advance * CLOCK_WIDTH_SCALE
    for token, glyph in spec['glyph_sets']['score']['glyphs'].items():
        width, advance = SCORE_METRICS[token]
        glyph['size'][0] = width * SCORE_WIDTH_SCALE
        glyph['advance'] = advance * SCORE_WIDTH_SCALE

    import io, subprocess
    base = Image.open(io.BytesIO(subprocess.check_output(
        ['git', 'show', 'HEAD:data/nfl2k5_scorebug_sprite/template.png'], cwd=ROOT))).convert('RGBA')
    body_box = _box(spec, 'body')
    sheet.paste(base.crop(tuple(body_box)), tuple(body_box[:2]))
    for name in [*(f'score_{d}' for d in '0123456789'), *(f'clock_{d}' for d in '0123456789'), 'colon']:
        box = _box(spec, name)
        sheet.paste(base.crop(tuple(box)), tuple(box[:2]))

    wing, _ = wing_cell(sizes['wing'])
    for name in ('wing', 'home_wing'):
        sheet.paste(wing, tuple(_box(spec, name)[:2]))
    sheet.paste(plate_cell(sizes['plate']), tuple(_box(spec, 'plate')[:2]))
    capsule = capsule_cell(sizes['capsule'])
    sheet.paste(capsule, tuple(_box(spec, 'capsule')[:2]))
    # The red state is the authored pill's own right cap: same rim, same outline.
    red = capsule.crop((capsule.width - sizes['red'][0], 0, capsule.width, sizes['red'][1]))
    sheet.paste(red, tuple(_box(spec, 'red')[:2]))
    sheet.paste(gloss_cell(sizes['plate_gloss']), tuple(_box(spec, 'plate_gloss')[:2]))
    sheet.paste(rim_cell(sizes['away_rim'], 'away'), tuple(_box(spec, 'away_rim')[:2]))
    sheet.paste(rim_cell(sizes['home_rim'], 'home'), tuple(_box(spec, 'home_rim')[:2]))
    for digit in '0123456789':
        name = 'score_' + digit
        box = _box(spec, name)
        # sb4: the 1-texel gray bevel read as a dirty outline at the 640-wide HUD
        # footprint; the broadcast score is solid white with only its edge AA.
        sheet.paste(sheet.crop(tuple(box)), tuple(box[:2]))

    from tools.scorebug_sprite import logo_zoom as lz
    accents_path = folder / 'team_accents.json'
    accents = json.loads(accents_path.read_text(encoding='utf-8')) if accents_path.is_file() else None
    plan = lz.plan(spec)['BUF']
    if plan['after'] != spec['logo_fit']['by_team']['BUF']['zoom']:
        spec['logo_fit']['by_team']['BUF']['zoom'] = plan['after']
        if accents is not None:
            accents['teams']['BUF']['logo_fit']['zoom'] = plan['after']
        previous = spec['provenance'].get('b778_sb2_logo_zoom')
        if previous:
            previous.setdefault('zoom', {})['BUF'] = [plan['before'], plan['after']]
    spec['provenance'][RECORD] = dict(
        job='b778 sb3 2026-10-23',
        request='Noah 10/23: border/glow, deeper team gradient over the logo, down-and-distance gradient',
        wing={k: WING[k] for k in WING},
        plate_rows=SB3_PLATE_ROWS,
        plate_source=[274, 38],
        capsule_source=[183, 40],
        rim=dict(
            cells=['away_rim', 'home_rim'],
            tint='the runtime lightens the wing shade for the rail; the sourced accent rim stays in the table',
            method='white coverage: outer rail glint, top corners and a centre-weighted lower lip; no new quad'),
        buf_zoom=dict(before=spec['provenance'].get('b778_sb2_logo_zoom', {}).get('zoom', {}).get('BUF', [plan['before']])[0],
                      after=plan['after']),
        buf='charging primary buffalo from data/nfl2k5_scorebug_assets/logos/buf.png',
        reference='reports/b72_s9/broadcast_away_median.png, broadcast_home_median.png and '
                  '.b77-scratch/b778/sb2/ref_bars.png (measurement only, no broadcast pixels)')
    spec['provenance'][CAPSULE_RECORD] = dict(
        job='b778 sb4 2026-10-23',
        request='Noah 10/23 02:00: one connected clock capsule and a smaller play clock',
        layout=list(CAPSULE_LAYOUT), source=[81, 16], design_source=list(CAPSULE_SOURCE),
        dividers_layout=[902.5, 1021.5], dividers_source=[round(v, 2) for v in CAPSULE_DIVIDERS],
        ink=dict(quarter=[32, 18], clock=[99, 26], play_clock=[15, 19]),
        fields=dict(quarter=19, clock=27, play_clock=19, scores=56),
        red_cell='the pill right cap, rim and outline included, drawn only at 5 seconds and under',
        reference='read-only 2026 Broncos at Chiefs still, sb3/ds/work/ref_full.png (measurement only)')
    spec['provenance'][PLATE_RECORD] = dict(
        job='b778 sb4 2026-10-23',
        request='Noah 10/23 02:00: the down and distance tab grows out of the bar top with a strong gradient',
        layout=list(PLATE_LAYOUT), source=[90, 19], design_source=list(PLATE_SOURCE), tab_rows=PLATE_TAB_ROWS,
        rows=PLATE_ROWS, shadow_rows=PLATE_SHADOW_ROWS, top_inset=0, bottom_inset=15,
        reference='read-only 2026 Broncos at Chiefs still, sb3/ds/work/ref_full.png (measurement only)')
    spec['provenance'][TAB_RECORD] = dict(
        job='b778 sb5 2026-10-23',
        request="Noah 10/23 03:40: the down and distance tab is a weird shape, not ESPN's smooth curves, and it "
                "does not blend into the possessing team's gradient",
        layout=list(PLATE_LAYOUT), source=[90, 19], design=list(TAB_DESIGN), supersample=TAB_SUPERSAMPLE,
        shoulder_bezier=[list(point) for point in TAB_FLARE], side_inset=TAB_SIDE, corner_radius=TAB_CORNER,
        bottom=TAB_BOTTOM, peak=TAB_PEAK, across=[list(row) for row in TAB_ACROSS],
        down=[list(row) for row in TAB_DOWN], band=[list(row) for row in TAB_BAND],
        glint=[list(row) for row in TAB_GLINT], rim=TAB_RIM, halo=TAB_HALO, halo_white=TAB_HALO_WHITE,
        tint='the possessing team: the midpoint of its wing display shade and its sourced plate accent (runtime)',
        reference='read-only 2026 Broncos at Chiefs still, sb3/ds/work/ref_full.png, and '
                  'reports/b72_s9/broadcast_away_median.png (measurement only, no broadcast pixels)')
    note = ('The sb3 rim cells are white coverage; the runtime lifts the wing shade for the rail, and the wing '
            'and plate remain coverage cells the native tints multiply. The sb4 capsule is white body with two '
            'measured dividers; its red state is the same right cap, and the plate is a tapered neutral tab.')
    if note not in spec.get('sampling', ''):
        spec['sampling'] = (spec.get('sampling', '') + ' ' + note).strip()

    from tools.scorebug_sprite import corner_shape as corner
    body = next(row for row in spec['static'] if row['name'] == 'body')
    shape_spec = dict(spec, static=[dict(body, cell='logo')] +
                      [row for row in spec['static'] if row['name'] in ('home_wing', 'body_right')])
    sheet = corner.shape(sheet, shape_spec)
    if not check:
        sheet.save(folder / 'template.png')
        (folder / 'layout.json').write_text(json.dumps(spec, indent=1) + '\n', encoding='utf-8', newline='\n')
        if accents is not None:
            accents_path.write_text(json.dumps(accents, indent=2) + '\n', encoding='utf-8', newline='\n')
        (LOGOS / 'buf.png').write_bytes(_png(buf))
    report = measurements(spec, sheet)
    report['buf_changed'] = _png(buf) != logos_before
    return report, spec


def _png(image):
    import io
    buffer = io.BytesIO()
    image.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    parser.add_argument('--check', action='store_true', help='measure without writing')
    parser.add_argument('--apply', action='store_true', help='write the cells (the default)')
    args = parser.parse_args(argv)
    report, spec = apply(args.folder, args.check)
    print(json.dumps(report, indent=1))
    if not args.check:
        print('authored', RECORD)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
