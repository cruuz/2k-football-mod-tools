"""Redraw the scorebar's Franchise records in ESPN's record style: bold proportional digits on a soft dark band.

Noah, stream 10/21 (c2-15): "the font on the records". The b76 s15 records were a monospaced one-texel pixel font
(every digit, the 1 included, 15 px wide) on an opaque navy box. On the 2026 ESPN bar a record such as "10-10" is set
in the bar's own bold broadcast face (the face of "3rd & 2", with a narrow 1), white, in the wing's lower outer corner,
over a darker band along the bottom of the wing that sits behind the team mark (Bills at Chiefs, ESPN NFL 2026).

Digits: the traced broadcast digit masks in data/nfl2k5_scorebug_assets/espn_glyphs.png (22 px cap, the medians the
bar's down label was traced from), levelled to coverage and area-filtered to the HUD footprint. A hyphen is drawn as
a bar of the digits' own stem weight. Each cell is 7 rows (17 px cap) and as many columns as its width covers at the
smallest footprint (16:9 with the widescreen contraction, 3 layout px per texel), so one texel draws as one HUD pixel.

Band: one cell per side (the cell is not mirrored by the engine), a dark wash along the bottom 28 px of the wing that
is darkest at the bar's outer edge and fades out before the score. It draws behind the team mark (z between the rims
and the mark), as on air, and keeps the same size for every record length.

python3 tools/scorebug_sprite/record_font.py [--folder FOLDER] [--check]
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = ROOT/'data/nfl2k5_scorebug_sprite'
GLYPHS = ROOT/'data/nfl2k5_scorebug_assets'
RECORD = 'b778_sb2_record_font'
CAP = 17                        # layout px (7 HUD rows)
ROWS = 7
PX_PER_TEXEL = 3.0              # layout px per texel at the smallest footprint (16:9, widescreen contraction)
SRC_CAP = 22                    # source mask rows
SRC_TRACK = 2.0                 # source px between digits (the broadcast label's spacing)
ADVANCE_GAP = 2.0               # layout px after each token
LEVEL_LO, LEVEL_HI = 96, 232    # source grey -> coverage 0 .. 1 (median background noise sits below 96)
HYPHEN = dict(width=8.0, height=4.6, centre=11.6, bearing=2.0)   # source px: stem weight, a little under mid-cap
BAND = dict(width=180.0, height=28.0, top=1022, outer=439.0, solid=0.5, alpha=0.5, feather_rows=2, levels=32, colour=(8, 10, 14), z=-18.25)
ROW_Y = 80                      # template rows 74..300 are free
ROW_PX = 1080/448               # layout px per HUD row
HALO = dict(alpha=0.6, colour=(6, 8, 12))   # one texel of soft dark ring around the ink, so a record reads on any mark
TOKENS = [str(n) for n in range(18)] + ['-' + str(n) for n in range(18)]
# The band's token is the record's text length. A regular season is at most 17 games, so "1-0" .. "10-6-1" is 3..6
# characters; two sets of four tokens keep the scene table (and the appended HUD bytes) at the b76 size.
TAB_LENGTHS = range(3, 7)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def source_masks():
    """Digit coverage masks (float arrays, SRC_CAP rows) from the traced broadcast sheet."""
    import numpy as np
    from PIL import Image
    meta = json.loads((GLYPHS/'espn_glyphs.json').read_text(encoding='utf-8'))
    sheet = np.asarray(Image.open(GLYPHS/'espn_glyphs.png').convert('L'), dtype=float)
    masks = {}
    for digit in '0123456789':
        x0, y0, x1, y1 = meta[digit]['box']
        y0 = y1-SRC_CAP                      # every digit to the shared baseline and cap ('6' rises one row)
        cell = sheet[y0:y1, x0:x1]
        cov = np.clip((cell-LEVEL_LO)/(LEVEL_HI-LEVEL_LO), 0, 1)
        cov = cov*cov*(3-2*cov)              # smoothstep: firm stroke cores, clean counters
        # Trim empty source columns so the digits sit at the broadcast spacing.
        cols = np.nonzero(cov.max(0) > .25)[0]
        masks[digit] = cov[:, cols[0]:cols[-1]+1]
    return masks


def hyphen_mask():
    import numpy as np
    h = HYPHEN
    width = int(math.ceil(h['width']+2*h['bearing']))
    ys = np.arange(SRC_CAP)+.5
    xs = np.arange(width)+.5
    def cover(c, lo, hi):            # exact 1-D coverage of [lo, hi] by the pixel centred at c
        return np.clip(np.minimum(c+.5, hi)-np.maximum(c-.5, lo), 0, 1)
    vy = cover(ys, h['centre']-h['height']/2, h['centre']+h['height']/2)
    vx = cover(xs, h['bearing'], h['bearing']+h['width'])
    return np.outer(vy, vx)


def compose(token, masks):
    import numpy as np
    parts = []
    for ch in token:
        parts.append(hyphen_mask() if ch == '-' else masks[ch])
    gap = np.zeros((SRC_CAP, int(SRC_TRACK)))
    out = parts[0]
    for i, part in enumerate(parts[1:], 1):
        out = np.concatenate([out, part] if token[i-1] == '-' else [out, gap, part], axis=1)
    return out


def token_cell(token, masks):
    """(texel coverage array ROWS x w, layout width)."""
    import numpy as np
    from PIL import Image
    src = compose(token, masks)
    width_px = src.shape[1]*CAP/SRC_CAP
    texels = max(1, int(round(width_px/PX_PER_TEXEL)))
    image = Image.fromarray(np.uint8(np.round(src*255)), 'L').resize((texels, ROWS), Image.Resampling.BOX)
    cov = np.asarray(image, dtype=float)/255
    cov = np.clip(cov*1.12, 0, 1)            # area filtering thins a bold stem below full cover; restore it
    return cov, texels*PX_PER_TEXEL


def with_halo(cov):
    """RGBA texels: the white ink plus a one-texel dark ring (the cell grows one texel on every side)."""
    import numpy as np
    from PIL import Image
    h, w = cov.shape
    pad = np.zeros((h+2, w+2)); pad[1:-1, 1:-1] = cov
    ring = np.zeros_like(pad)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            ring = np.maximum(ring, np.roll(np.roll(pad, dy, 0), dx, 1))
    halo = HALO['alpha']*ring
    alpha = pad+halo*(1-pad)
    out = np.zeros((h+2, w+2, 4), np.uint8)
    safe = np.where(alpha > 0, alpha, 1)
    for k in range(3):
        out[..., k] = np.uint8(np.round(np.clip((255*pad+HALO['colour'][k]*halo*(1-pad))/safe, 0, 255)))
    out[..., 3] = np.uint8(np.round(np.clip(alpha, 0, 1)*255))
    return Image.fromarray(out, 'RGBA')


def band_cell(side):
    """Band coverage at texel resolution, darkest at the bar's outer edge (away left, home right)."""
    import numpy as np
    b = BAND
    w = int(b['width']/PX_PER_TEXEL)
    h = int(b['height']*448/1080)             # rows at the HUD footprint
    a = np.zeros((h, w))
    for x in range(w):
        t = (x+.5)/w                           # 0 at the outer edge
        horiz = 1.0 if t <= b['solid'] else max(0.0, 1-((t-b['solid'])/(1-b['solid'])))
        horiz = horiz*horiz*(3-2*horiz)
        for y in range(h):
            vert = min(1.0, (y+.5)/b['feather_rows'])
            a[y, x] = b['alpha']*horiz*vert
    # A few exact alpha levels: the P8 atlas palette keeps every one, so the fade has no quantization steps.
    a = np.round(a*b['levels'])/b['levels']
    if side == 'home':
        a = a[:, ::-1]
    return a


def rgba(cov, colour=(255, 255, 255)):
    import numpy as np
    from PIL import Image
    h, w = cov.shape
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = colour
    out[..., 3] = np.uint8(np.round(np.clip(cov, 0, 1)*255))
    return Image.fromarray(out, 'RGBA')


def apply(spec, image):
    """Return (spec, image) with the record cells, glyph sets and fields replaced."""
    from PIL import Image
    masks = source_masks()
    image = image.copy()
    # Clear the old record row (cells record_d*, record_m*, record_tab) so no stale art stays in the template.
    for name in [n for n in spec['cells'] if n.startswith('record_')]:
        x0, y0, x1, y1 = spec['cells'][name]['box']
        image.paste(Image.new('RGBA', (x1-x0, y1-y0), (0, 0, 0, 0)), (x0, y0))
        del spec['cells'][name]
    x = 1
    glyphs = {}
    for token in TOKENS:
        cov, width = token_cell(token, masks)
        name = 'record_' + ('m'+token[1:] if token[0] == '-' else 'd'+token)
        cell = with_halo(cov)
        image.paste(cell, (x, ROW_Y))
        spec['cells'][name] = {'box': [x, ROW_Y, x+cell.width, ROW_Y+cell.height]}
        # The ring texel on each side widens the quad by one texel and raises it by one row; the advance keeps the
        # ink spacing, so the rings of neighbouring tokens overlap.
        glyphs[token] = {'cell': name, 'size': [width+2*PX_PER_TEXEL, (ROWS+2)*ROW_PX], 'advance': width+ADVANCE_GAP,
                         'raise': ROW_PX}
        x += cell.width+2
    spec['glyph_sets']['record'] = {'cap_height': CAP, 'glyphs': glyphs}
    y = ROW_Y+ROWS+5
    x = 1
    for side in ('away', 'home'):
        cell = rgba(band_cell(side), BAND['colour'])
        name = 'record_band_'+side
        image.paste(cell, (x, y))
        spec['cells'][name] = {'box': [x, y, x+cell.width, y+cell.height]}
        x += cell.width+2
    size = [BAND['width'], BAND['height']]
    band = lambda side: {'cap_height': BAND['height'], 'glyphs': {str(n): {'cell': 'record_band_'+side, 'size': list(size),
                                                                        'advance': BAND['width'], 'raise': 0} for n in TAB_LENGTHS}}
    spec['glyph_sets']['record_tab'] = band('away')
    spec['glyph_sets']['record_tab_home'] = band('home')
    fields = {f['name']: f for f in spec['fields']}
    bar = next(r['box'] for r in spec['static'] if r['name'] == 'body')
    left, right = BAND['outer'], bar[2]-(BAND['outer']-bar[0])     # mirrored about the bar
    top, bottom = BAND['top'], BAND['top']+BAND['height']
    # Records: the ink keeps its b76 s15 place (447 / 1472, rows 1027..1044); the ring texel sits outside it.
    for name, sign in (('away_record', -1), ('home_record', 1)):
        f = fields[name]
        f['anchor'] = [f['anchor'][0]+sign*PX_PER_TEXEL, f['anchor'][1]]
        f['box'] = [f['box'][0]-PX_PER_TEXEL, f['box'][1], f['box'][2]+PX_PER_TEXEL, f['box'][3]]
    fields['away_record_tab'].update(box=[left, top, left+BAND['width'], bottom], anchor=[left, top], size=BAND['height'],
                                     glyph_set='record_tab', z=BAND['z'])
    fields['home_record_tab'].update(box=[right-BAND['width'], top, right, bottom], anchor=[right, top], size=BAND['height'],
                                     glyph_set='record_tab_home', z=BAND['z'])
    return spec, image


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER)
    parser.add_argument('--check', action='store_true', help='report without writing')
    args = parser.parse_args()
    from PIL import Image
    layout = args.folder/'layout.json'
    spec = json.loads(layout.read_text(encoding='utf-8'))
    raw = (args.folder/'template.png').read_bytes()
    if spec['provenance'].get(RECORD):
        print('already redrawn: template', _sha(raw))
        return 0
    if args.check:
        print('not redrawn: template', _sha(raw))
        return 0
    with Image.open(args.folder/'template.png') as image:
        spec, shaped = apply(spec, image.convert('RGBA'))
    spec['provenance'][RECORD] = dict(
        job='b778 sb2 2026-10-22', request='Noah 10/21 stream c2-15: the font on the records',
        digits='data/nfl2k5_scorebug_assets/espn_glyphs.png traced broadcast digit medians, levels %d..%d, smoothstep, '
               'area-filtered to 7 rows at 3 layout px per texel' % (LEVEL_LO, LEVEL_HI),
        hyphen='drawn: a bar of the digit stem weight (source px %s)' % json.dumps(HYPHEN),
        band='drawn: %s; one cell per side, behind the team mark' % json.dumps(BAND),
        reference='2026 ESPN NFL Bills at Chiefs bar with records (measurement only, no broadcast pixels)',
        template_before_sha256=_sha(raw))
    shaped.save(args.folder/'template.png', optimize=True)
    layout.write_text(json.dumps(spec, indent=1)+'\n', encoding='utf-8', newline='\n')
    print('redrawn: template', _sha((args.folder/'template.png').read_bytes()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
